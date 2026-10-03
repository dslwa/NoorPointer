package pl.noorpointer.dto;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
import java.util.List;

public record PromptCheckRequest(
    @NotNull @Pattern(regexp = "input|output") String direction,
    @NotNull @Size(min = 1, max = 50) List<@NotNull @Valid Message> messages) {
  public record Message(
      @NotNull @Pattern(regexp = "user|assistant|system|tool") String role,
      @NotBlank @Size(max = 200_000) String content) {}
}
