package pl.noorpointer.dto;

import jakarta.validation.constraints.Positive;

public record PolicyPublicationRequest(@Positive long version) {}
