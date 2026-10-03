package pl.noorpointer.controller.compatibility;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;
import pl.noorpointer.document.DocumentService;
import pl.noorpointer.dto.AuditReceipt;
import pl.noorpointer.dto.SignatureFeedResponse;
import pl.noorpointer.service.AuditService;
import pl.noorpointer.service.PolicyService;
import pl.noorpointer.service.SignatureService;
import pl.noorpointer.web.CachedResponses;

/** Compatibility with existing gateway clients. New clients use the resource API under /api/v1. */
@RestController
public class LegacyGatewayController {
  private final PolicyService policies;
  private final SignatureService signatures;
  private final AuditService audit;
  private final CachedResponses cached;
  private final DocumentService documents;

  public LegacyGatewayController(
      PolicyService policies,
      SignatureService signatures,
      AuditService audit,
      CachedResponses cached,
      DocumentService documents) {
    this.policies = policies;
    this.signatures = signatures;
    this.audit = audit;
    this.cached = cached;
    this.documents = documents;
  }

  @GetMapping({"/api/gateway/policy", "/api/v1/policies"})
  public ResponseEntity<JsonNode> policy(
      @RequestHeader(value = "If-None-Match", required = false) String previous) {
    return cached.of(policies.gatewayPolicy(), previous);
  }

  @GetMapping("/api/gateway/signatures")
  public ResponseEntity<SignatureFeedResponse> signatures(
      @RequestHeader(value = "If-None-Match", required = false) String previous) {
    return cached.of(signatures.feed(), previous);
  }

  @PostMapping("/api/gateway/events")
  public AuditReceipt ingest(@RequestBody JsonNode event) {
    return audit.ingest(event);
  }

  @GetMapping("/api/contracts/{name}")
  public JsonNode schema(@PathVariable String name) {
    return documents.schema(name);
  }
}
