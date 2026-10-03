package pl.noorpointer.dto;

import java.util.List;
import java.util.Map;

public record DashboardResponse(
    Map<String, Object> summary,
    List<Map<String, Object>> budgets,
    ActivePolicyResponse activePolicy,
    long controlsEnabled,
    long controlsTotal,
    boolean demoEnabled) {}
