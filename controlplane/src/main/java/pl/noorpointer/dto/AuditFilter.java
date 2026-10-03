package pl.noorpointer.dto;

import java.time.Instant;

public record AuditFilter(String action, String category, String agent, Instant from, Instant to) {}
