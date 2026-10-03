package pl.noorpointer.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import pl.noorpointer.dto.PromptCheckRequest;

/** Authenticated transport to Go. The gateway owns all checks, decisions and audit writes. */
@Service
public class PromptCheckService {
  private final URI endpoint;
  private final String token;
  private final ObjectMapper mapper;
  private final HttpClient client =
      HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();

  public PromptCheckService(
      @Value("${control-plane.gateway-url}") String gatewayUrl,
      @Value("${control-plane.admin-token}") String token,
      ObjectMapper mapper) {
    this.endpoint = URI.create(gatewayUrl.replaceAll("/+$", "") + "/admin/check");
    this.token = token;
    this.mapper = mapper;
  }

  public JsonNode check(PromptCheckRequest input) {
    try {
      var request =
          HttpRequest.newBuilder(endpoint)
              .timeout(Duration.ofSeconds(20))
              .header("Authorization", "Bearer " + token)
              .header("Content-Type", "application/json")
              .POST(HttpRequest.BodyPublishers.ofString(mapper.writeValueAsString(input)))
              .build();
      var response = client.send(request, HttpResponse.BodyHandlers.ofString());
      if (response.statusCode() != 200) {
        String message =
            response.statusCode() == 404
                ? "Gateway check endpoint is unavailable. Rebuild the Go gateway."
                : "Gateway check failed (HTTP " + response.statusCode() + ")";
        if (response.statusCode() == 400 || response.statusCode() == 413) {
          throw new ResponseStatusException(
              HttpStatus.valueOf(response.statusCode()), "Gateway rejected the check request");
        }
        throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, message);
      }
      JsonNode body = mapper.readTree(response.body());
      if (body == null || !body.isObject() || !body.path("decision").isTextual()) {
        throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Invalid gateway check response");
      }
      return body;
    } catch (InterruptedException e) {
      Thread.currentThread().interrupt();
      throw new ResponseStatusException(
          HttpStatus.SERVICE_UNAVAILABLE, "Gateway request interrupted");
    } catch (IOException e) {
      throw new ResponseStatusException(
          HttpStatus.BAD_GATEWAY, "Cannot reach the Go gateway or read its response");
    }
  }
}
