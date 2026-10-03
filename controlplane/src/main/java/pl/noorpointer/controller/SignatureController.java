package pl.noorpointer.controller;

import com.fasterxml.jackson.databind.JsonNode;
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import pl.noorpointer.service.SignatureService;

@RestController
@RequestMapping("/api/v1/signatures")
public class SignatureController {
  private final SignatureService signatures;

  public SignatureController(SignatureService signatures) {
    this.signatures = signatures;
  }

  @GetMapping("/{id}")
  public JsonNode get(@PathVariable String id) {
    return signatures.get(id);
  }

  @PostMapping(consumes = "application/json")
  public ResponseEntity<JsonNode> create(@RequestBody JsonNode signature) {
    return created(signatures.create(signature));
  }

  @PostMapping(consumes = {"text/plain", "application/yaml", "application/x-yaml"})
  public ResponseEntity<JsonNode> createFromDocument(@RequestBody String document) {
    return created(signatures.createFromDocument(document));
  }

  private ResponseEntity<JsonNode> created(JsonNode created) {
    return ResponseEntity.created(URI.create("/api/v1/signatures/" + created.path("id").asText()))
        .body(created);
  }
}
