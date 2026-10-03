package pl.noorpointer.dto;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record DocumentRequest(@NotBlank @Size(max = 1_000_000) String document) {}
