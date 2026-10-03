package pl.noorpointer.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.ArrayList;
import java.util.HashSet;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
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
    repository.replaceAll(signatures);
    return feed();
  }
}
