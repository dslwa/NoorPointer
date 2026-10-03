package pl.noorpointer.controller;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import pl.noorpointer.document.DocumentService;

@RestController
@RequestMapping("/api/v1")
public class DocumentController {
  private final DocumentService documents;

  public DocumentController(DocumentService documents) {
    this.documents = documents;
  }

  @GetMapping("/policy-profiles/{name}")
  public JsonNode profile(@PathVariable String name) {
    return documents.profile(name);
  }

  @GetMapping("/schemas/{name}")
  public JsonNode schema(@PathVariable String name) {
    return documents.schema(name);
  }
}
