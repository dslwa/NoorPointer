package pl.noorpointer.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record PolicyDraftRequest(
    @NotBlank @Size(max = 120) String name,
    @Size(max = 1000) String description,
    @NotBlank @Size(max = 1_000_000) String document) {}
