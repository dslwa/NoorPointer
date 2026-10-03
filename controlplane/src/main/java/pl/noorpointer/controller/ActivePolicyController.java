package pl.noorpointer.controller;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import pl.noorpointer.dto.ActivePolicyResponse;
import pl.noorpointer.dto.PolicyPublicationRequest;
import pl.noorpointer.service.PolicyService;
import pl.noorpointer.web.CachedResponses;

@RestController
@RequestMapping("/api/v1/active-policy")
public class ActivePolicyController {
  private final PolicyService policies;
  private final CachedResponses cached;

  public ActivePolicyController(PolicyService policies, CachedResponses cached) {
    this.policies = policies;
    this.cached = cached;
  }

  @GetMapping
  public ActivePolicyResponse get() {
    return policies.active();
  }

  @PutMapping
  public ActivePolicyResponse replace(@Valid @RequestBody PolicyPublicationRequest request) {
    return policies.publish(request.version());
  }

  @GetMapping("/document")
  public ResponseEntity<JsonNode> document(
      @RequestHeader(value = "If-None-Match", required = false) String previous) {
    return cached.of(policies.gatewayPolicy(), previous);
  }
}
