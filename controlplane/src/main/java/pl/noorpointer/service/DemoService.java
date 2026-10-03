package pl.noorpointer.service;

import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import pl.noorpointer.document.DocumentService;
import pl.noorpointer.dto.DemoBatchResponse;

@Service
public class DemoService {
  private final PolicyService policies;
  private final AuditService audit;
  private final DocumentService documents;
  private final boolean demoEnabled;

  public DemoService(
      PolicyService policies,
      AuditService audit,
      DocumentService documents,
      @Value("${control-plane.demo-enabled}") boolean demoEnabled) {
    this.policies = policies;
    this.audit = audit;
    this.documents = documents;
    this.demoEnabled = demoEnabled;
  }

  public boolean isEnabled() {
    return demoEnabled;
  }

  @Transactional
  public DemoBatchResponse createBatch() {
    if (!demoEnabled) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Demo is disabled");
    String[] actions = {"allow", "block", "allow", "redact", "block", "allow"};
    String[] controls = {
      "model_allowlist", "prompt_injection", "model_allowlist", "pii_regex", "secrets", "mcp_tools"
    };
    String[] categories = {
      "unclassified", "LLM01:2025", "unclassified", "LLM02:2025", "LLM02:2025", "unclassified"
    };
    long version = policies.active().revision().version();
    String batchId = UUID.randomUUID().toString();
    int count = 0;
    for (int i = 0; i < 18; i++) {
      int index = i % actions.length;
      Instant time = Instant.now().minusSeconds((i % 7) * 86400L + 60L * i);
      String request = UUID.randomUUID().toString();
      ObjectNode event = (ObjectNode) documents.read("{}");
      event.put("id", UUID.randomUUID().toString());
      event.put("occurred_at", time.toString());
      event.put("kind", "decision");
      event.put("request_id", request);
      event.put("agent_id", i % 2 == 0 ? "finance-agent" : "research-agent");
      event.put("team", i % 2 == 0 ? "finance" : "research");
      event.put("model", "llama3.1:8b");
      event.put("action", actions[index]);
      event.put("control", controls[index]);
      event.put("category", categories[index]);
      event.put("severity", actions[index].equals("block") ? "high" : "info");
      event.put("policy_version", version);
      event.put("latency_ms", 3 + index * 2);
      event.put("message", "Synthetic demo event: " + controls[index]);
      event.set("context", documents.read("{\"demo\":true}"));
      event.withObject("/context").put("demo_batch_id", batchId);
      audit.ingest(event);
      count++;
      if (!actions[index].equals("block")) {
        event.put("id", UUID.randomUUID().toString());
        event.put("kind", "usage");
        event.put("action", "allow");
        event.put("tokens", 400 + i * 10);
        event.put("cost_usd", 0.004);
        event.put("gpu_seconds", 0.5);
        event.put("control", "usage");
        event.put("message", "Synthetic usage report");
        audit.ingest(event);
        count++;
      }
    }
    return new DemoBatchResponse(batchId, count, true);
  }
}
