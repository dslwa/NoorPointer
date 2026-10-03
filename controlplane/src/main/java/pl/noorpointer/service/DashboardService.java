package pl.noorpointer.service;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.stereotype.Service;
import pl.noorpointer.dto.DashboardResponse;

@Service
public class DashboardService {
  private final PolicyService policies;
  private final AuditService audit;
  private final DemoService demo;

  public DashboardService(PolicyService policies, AuditService audit, DemoService demo) {
    this.policies = policies;
    this.audit = audit;
    this.demo = demo;
  }

  public DashboardResponse get() {
    var active = policies.active();
    var policy = active.revision().document();
    long enabled = 0, total = 0;
    for (JsonNode control : policy.path("controls")) {
      total++;
      if (control.path("enabled").asBoolean()) enabled++;
    }
    return new DashboardResponse(
        audit.summary(), audit.budgets(policy), active, enabled, total, demo.isEnabled());
  }
}
