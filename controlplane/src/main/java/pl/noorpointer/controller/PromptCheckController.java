package pl.noorpointer.controller;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import pl.noorpointer.dto.PromptCheckRequest;
import pl.noorpointer.service.PromptCheckService;

@RestController
public class PromptCheckController {
  private final PromptCheckService gateway;

  public PromptCheckController(PromptCheckService gateway) {
    this.gateway = gateway;
  }

  @PostMapping("/gateway/check")
  public JsonNode check(@Valid @RequestBody PromptCheckRequest input) {
    return gateway.check(input);
  }
}
