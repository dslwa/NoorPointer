package pl.noorpointer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest(
    properties = {
      "spring.datasource.url=${TEST_DATABASE_URL:jdbc:postgresql://localhost:5432/noorpointer_test?currentSchema=controlplane_test}",
      "spring.datasource.username=${TEST_DATABASE_USER:noor}",
      "spring.datasource.password=${TEST_DATABASE_PASSWORD:noorpass}",
      "spring.flyway.schemas=controlplane_test",
      "spring.flyway.default-schema=controlplane_test",
      "control-plane.admin-token=test-admin",
      "control-plane.gateway-token=test-gateway"
    })
@AutoConfigureMockMvc
class PromptCheckIntegrationTest {
  private static final String INPUT =
      """
      {"direction":"input","messages":[{"role":"user","content":"Hello"}]}
      """;
  private static final String REPORT =
      """
{"decision":"block","code":"PROMPT_INJECTION_DETECTED","message":"prompt injection score 0.97",
 "policy_version":12,"mode":"enforce","findings":[],
 "semantic":[{"check":"CHECK_PROMPT_INJECTION","status":"STATUS_OK","score":0.97,"categories":[]}],
 "messages":[{"role":"user","content":"Hello"}],"audit_saved":true,"audit_event_id":"check-1"}
""";
  private static final AtomicInteger calls = new AtomicInteger();
  private static final AtomicInteger status = new AtomicInteger(200);
  private static final AtomicReference<String> body = new AtomicReference<>(REPORT);
  private static final AtomicReference<String> authorization = new AtomicReference<>();
  private static final AtomicReference<String> submitted = new AtomicReference<>();
  private static final HttpServer gateway = createGateway();
  @Autowired MockMvc mvc;

  private static HttpServer createGateway() {
    try {
      var server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
      server.createContext(
          "/admin/check",
          exchange -> {
            calls.incrementAndGet();
            authorization.set(exchange.getRequestHeaders().getFirst("Authorization"));
            submitted.set(
                new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
            byte[] bytes = body.get().getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set("Content-Type", "application/json");
            exchange.sendResponseHeaders(status.get(), bytes.length);
            exchange.getResponseBody().write(bytes);
            exchange.close();
          });
      server.start();
      return server;
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }

  @DynamicPropertySource
  static void gatewayUrl(DynamicPropertyRegistry properties) {
    properties.add(
        "control-plane.gateway-url", () -> "http://127.0.0.1:" + gateway.getAddress().getPort());
  }

  @AfterAll
  static void stopGateway() {
    gateway.stop(0);
  }

  @BeforeEach
  void reset() {
    calls.set(0);
    status.set(200);
    body.set(REPORT);
  }

  @Test
  void requiresPanelAdministratorBeforeContactingGateway() throws Exception {
    mvc.perform(post("/gateway/check").contentType(MediaType.APPLICATION_JSON).content(INPUT))
        .andExpect(status().isUnauthorized());
    mvc.perform(
            post("/gateway/check")
                .header("Authorization", "Bearer test-gateway")
                .contentType(MediaType.APPLICATION_JSON)
                .content(INPUT))
        .andExpect(status().isForbidden());
    assertThat(calls).hasValue(0);
  }

  @Test
  void forwardsToGoWithServerTokenAndPreservesDecisionAndAuditReceipt() throws Exception {
    mvc.perform(
            post("/gateway/check")
                .header("Authorization", "Bearer test-admin")
                .contentType(MediaType.APPLICATION_JSON)
                .content(INPUT))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.decision").value("block"))
        .andExpect(jsonPath("$.policy_version").value(12))
        .andExpect(jsonPath("$.semantic[0].score").value(0.97))
        .andExpect(jsonPath("$.audit_saved").value(true))
        .andExpect(jsonPath("$.audit_event_id").value("check-1"));
    assertThat(authorization).hasValue("Bearer test-admin");
    assertThat(submitted.get())
        .contains("\"direction\":\"input\"", "\"content\":\"Hello\"")
        .doesNotContain("threshold");
    assertThat(calls).hasValue(1);
  }

  @Test
  void rejectsInvalidInputWithoutContactingGo() throws Exception {
    for (String input :
        new String[] {
          "{\"direction\":\"invalid\",\"messages\":[]}",
          "{\"direction\":\"input\",\"messages\":[{\"role\":\"invalid\",\"content\":\"hello\"}]}",
          "{\"direction\":\"input\",\"messages\":[{\"role\":\"user\",\"content\":\" \"}]}",
          "{\"direction\":\"input\",\"messages\":[null]}",
          "{\"direction\":\"input\",\"messages\":[],\"threshold\":0.1}"
        })
      mvc.perform(
              post("/gateway/check")
                  .header("Authorization", "Bearer test-admin")
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(input))
          .andExpect(status().isBadRequest());
    assertThat(calls).hasValue(0);
  }

  @Test
  void reportsGatewayErrorsInsteadOfInventingACleanVerdict() throws Exception {
    status.set(503);
    body.set("{\"error\":\"policy not loaded\"}");
    mvc.perform(
            post("/gateway/check")
                .header("Authorization", "Bearer test-admin")
                .contentType(MediaType.APPLICATION_JSON)
                .content(INPUT))
        .andExpect(status().isBadGateway())
        .andExpect(jsonPath("$.message").value("Gateway check failed (HTTP 503)"));
    status.set(200);
    body.set("<html>not a check</html>");
    mvc.perform(
            post("/gateway/check")
                .header("Authorization", "Bearer test-admin")
                .contentType(MediaType.APPLICATION_JSON)
                .content(INPUT))
        .andExpect(status().isBadGateway());
    body.set("{\"ready\":true}");
    mvc.perform(
            post("/gateway/check")
                .header("Authorization", "Bearer test-admin")
                .contentType(MediaType.APPLICATION_JSON)
                .content(INPUT))
        .andExpect(status().isBadGateway());
  }
}
