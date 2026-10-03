package pl.noorpointer.controller;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Positive;
import java.net.URI;
import java.util.List;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import pl.noorpointer.dto.PolicyDraftRequest;
import pl.noorpointer.dto.PolicyRevisionResponse;
import pl.noorpointer.service.PolicyService;

@RestController
@RequestMapping("/api/v1/policy-revisions")
public class PolicyRevisionController {
  private final PolicyService policies;

  public PolicyRevisionController(PolicyService policies) {
    this.policies = policies;
  }

  @GetMapping
  public List<PolicyRevisionResponse> list() {
    return policies.list();
  }

  @GetMapping("/{version}")
  public PolicyRevisionResponse get(@PathVariable @Positive long version) {
    return policies.get(version);
  }

  @DeleteMapping("/{version}")
  public ResponseEntity<Void> delete(@PathVariable @Positive long version) {
    policies.delete(version);
    return ResponseEntity.noContent().build();
  }

  @PostMapping
  public ResponseEntity<PolicyRevisionResponse> create(
      @Valid @RequestBody PolicyDraftRequest draft) {
    var revision = policies.create(draft);
    return ResponseEntity.created(URI.create("/api/v1/policy-revisions/" + revision.version()))
        .body(revision);
  }
}
