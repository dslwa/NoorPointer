package pl.noorpointer.config;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.UsernamePasswordAuthenticationFilter;
import org.springframework.web.filter.OncePerRequestFilter;
import pl.noorpointer.dto.ApiError;

@Configuration
public class SecurityConfig {
  @Bean
  SecurityFilterChain security(
      HttpSecurity http,
      @Value("${control-plane.admin-token}") String adminToken,
      @Value("${control-plane.gateway-token}") String gatewayToken,
      ObjectMapper mapper)
      throws Exception {
    if (adminToken.isBlank() || gatewayToken.isBlank() || adminToken.equals(gatewayToken)) {
      throw new IllegalStateException("Admin and gateway tokens must be non-empty and different");
    }
    var filter =
        new OncePerRequestFilter() {
          @Override
          protected void doFilterInternal(
              HttpServletRequest request, HttpServletResponse response, FilterChain chain)
              throws IOException, ServletException {
            String authorization = request.getHeader("Authorization");
            if (authorization != null && authorization.startsWith("Bearer ")) {
              String token = authorization.substring(7);
              String role =
                  matches(token, adminToken)
                      ? "ADMIN"
                      : matches(token, gatewayToken) ? "GATEWAY" : null;
              if (role != null) {
                SecurityContextHolder.getContext()
                    .setAuthentication(
                        new UsernamePasswordAuthenticationToken(
                            role.toLowerCase(),
                            null,
                            List.of(new SimpleGrantedAuthority("ROLE_" + role))));
              }
            }
            chain.doFilter(request, response);
          }
        };
    return http.csrf(csrf -> csrf.disable())
        .sessionManagement(
            session -> session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
        .authorizeHttpRequests(
            auth ->
                auth.requestMatchers(
                        "/",
                        "/index.html",
                        "/assets/**",
                        "/favicon.svg",
                        "/actuator/health",
                        "/error")
                    .permitAll()
                    .requestMatchers(
                        org.springframework.http.HttpMethod.GET,
                        "/api/v1/active-policy/document",
                        "/api/v1/signature-feed",
                        "/api/v1/schemas/**",
                        "/api/gateway/policy",
                        "/api/gateway/signatures",
                        "/api/v1/policies",
                        "/api/contracts/**")
                    .hasAnyRole("ADMIN", "GATEWAY")
                    .requestMatchers(
                        org.springframework.http.HttpMethod.POST,
                        "/api/v1/audit-events",
                        "/api/v1/audit/events",
                        "/api/gateway/events")
                    .hasAnyRole("ADMIN", "GATEWAY")
                    .requestMatchers("/api/**", "/actuator/prometheus")
                    .hasRole("ADMIN")
                    .anyRequest()
                    .denyAll())
        .exceptionHandling(
            errors ->
                errors
                    .authenticationEntryPoint(
                        (req, res, ex) -> error(mapper, req, res, 401, "Authentication required"))
                    .accessDeniedHandler(
                        (req, res, ex) -> error(mapper, req, res, 403, "Access denied")))
        .addFilterBefore(filter, UsernamePasswordAuthenticationFilter.class)
        .build();
  }

  private static boolean matches(String provided, String expected) {
    return MessageDigest.isEqual(
        provided.getBytes(StandardCharsets.UTF_8), expected.getBytes(StandardCharsets.UTF_8));
  }

  private static void error(
      ObjectMapper mapper,
      HttpServletRequest request,
      HttpServletResponse response,
      int status,
      String message)
      throws IOException {
    response.setStatus(status);
    response.setContentType("application/json");
    mapper.writeValue(
        response.getOutputStream(),
        new ApiError(status, message, request.getRequestURI(), Instant.now()));
  }
}
