package pl.noorpointer.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.HashSet;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import pl.noorpointer.document.DocumentService;
import pl.noorpointer.dto.SignatureFeedResponse;
import pl.noorpointer.repository.SignatureRepository;

@Service
public class SignatureService {
  private final SignatureRepository repository;
  private final DocumentService documents;

  public SignatureService(SignatureRepository repository, DocumentService documents) {
    this.repository = repository;
    this.documents = documents;
  }

  public SignatureFeedResponse feed() {
    return new SignatureFeedResponse(repository.findAll());
  }

  public JsonNode get(String id) {
    return repository
        .findById(id)
        .orElseThrow(
            () -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Signature not found"));
  }

  @Transactional
  public JsonNode createFromDocument(String text) {
    return create(documents.parse(text));
  }

  @Transactional
  public JsonNode create(JsonNode signature) {
    var feed = documents.read("{\"signatures\":[]}");
    ((com.fasterxml.jackson.databind.node.ArrayNode) feed.path("signatures")).add(signature);
    documents.validate("signatures", feed);
    repository.lockForWrite();
    if (repository.findById(signature.path("id").asText()).isPresent()) {
      throw new ResponseStatusException(HttpStatus.CONFLICT, "Signature ID already exists");
    }
    if (repository.count() >= 1000) {
      throw new ResponseStatusException(
          HttpStatus.CONFLICT, "The feed is limited to 1,000 signatures");
    }
    repository.insert(signature);
    return signature;
  }

  @Transactional
  public SignatureFeedResponse replace(String text) {
    JsonNode node = documents.parse(text);
    documents.validate("signatures", node);
    var ids = new HashSet<String>();
    var signatures = new ArrayList<JsonNode>();
    for (JsonNode signature : node.path("signatures")) {
      if (!ids.add(signature.path("id").asText()))
        throw new IllegalArgumentException("Duplicate signature ID");
      signatures.add(signature);
    }
    repository.lockForWrite();
    repository.replaceAll(signatures);
    return feed();
  }
}
