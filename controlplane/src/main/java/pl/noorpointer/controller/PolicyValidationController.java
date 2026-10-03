package pl.noorpointer.controller;

import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import pl.noorpointer.dto.DocumentRequest;
import pl.noorpointer.dto.ValidationResponse;
import pl.noorpointer.service.PolicyService;

@RestController
@RequestMapping("/api/v1/policy-validations")
public class PolicyValidationController {
  private final PolicyService policies;

  public PolicyValidationController(PolicyService policies) {
    this.policies = policies;
  }

  @PostMapping
  public ValidationResponse validate(@Valid @RequestBody DocumentRequest request) {
    policies.validate(request.document());
    return new ValidationResponse(true);
  }
}
