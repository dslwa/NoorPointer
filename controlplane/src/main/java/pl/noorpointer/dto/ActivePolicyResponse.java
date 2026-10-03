package pl.noorpointer.dto;

import java.time.Instant;

public record ActivePolicyResponse(PolicyRevisionResponse revision, Instant publishedAt) {}
