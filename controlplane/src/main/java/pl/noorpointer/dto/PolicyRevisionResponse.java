package pl.noorpointer.dto;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;

public record PolicyRevisionResponse(
    long version, String name, String description, Instant createdAt, JsonNode document) {}
