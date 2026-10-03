package pl.noorpointer.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import pl.noorpointer.document.DocumentService;
import pl.noorpointer.dto.ActivePolicyResponse;
import pl.noorpointer.dto.PolicyDraftRequest;
import pl.noorpointer.dto.PolicyRevisionResponse;
import pl.noorpointer.repository.PolicyRepository;

@Service
public class PolicyService {
  private final PolicyRepository repository;
  private final DocumentService documents;

  public PolicyService(PolicyRepository repository, DocumentService documents) {
    this.repository = repository;
    this.documents = documents;
  }

  @Transactional
  public void initializeDefaults() {
    if (!repository.isEmpty()) return;
    long balanced = 0;
    for (String profile : List.of("permissive", "balanced", "strict")) {
      var revision =
          create(
              new PolicyDraftRequest(
                  profile,
                  "Built-in " + profile + " profile",
                  documents.write(documents.profile(profile))));
      if (profile.equals("balanced")) balanced = revision.version();
    }
    repository.initializeActive(balanced);
  }

  @Transactional
  public PolicyRevisionResponse create(PolicyDraftRequest draft) {
    JsonNode node = documents.parse(draft.document());
    documents.validate("policy", node);
    long version =
        repository.insert(
            draft.name().trim(),
            draft.description() == null ? "" : draft.description(),
            documents.write(node),
            Instant.now());
    ((ObjectNode) node).put("version", version);
    repository.updateDocument(version, documents.write(node));
    return get(version);
  }

  public List<PolicyRevisionResponse> list() {
    return repository.findAll();
  }

  public PolicyRevisionResponse get(long version) {
    return repository
        .findByVersion(version)
        .orElseThrow(
            () -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Policy revision not found"));
  }

  public ActivePolicyResponse active() {
    return repository
        .findActive()
        .orElseThrow(
            () ->
                new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "No policy published"));
  }

  @Transactional
  public ActivePolicyResponse publish(long version) {
    get(version);
    if (active().revision().version() != version) repository.publish(version);
    return active();
  }

  public JsonNode gatewayPolicy() {
    return active().revision().document();
  }

  public void validate(String document) {
    documents.validate("policy", documents.parse(document));
  }
}
