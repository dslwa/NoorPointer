package pl.noorpointer.controller;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import pl.noorpointer.dto.DocumentRequest;
import pl.noorpointer.dto.SignatureFeedResponse;
import pl.noorpointer.service.SignatureService;
import pl.noorpointer.web.CachedResponses;

@RestController
@RequestMapping("/api/v1/signature-feed")
public class SignatureFeedController {
  private final SignatureService signatures;
  private final CachedResponses cached;

  public SignatureFeedController(SignatureService signatures, CachedResponses cached) {
    this.signatures = signatures;
    this.cached = cached;
  }

  @GetMapping
  public ResponseEntity<SignatureFeedResponse> get(
      @RequestHeader(value = "If-None-Match", required = false) String previous) {
    return cached.of(signatures.feed(), previous);
  }

  @PutMapping
  public SignatureFeedResponse replace(@Valid @RequestBody DocumentRequest request) {
    return signatures.replace(request.document());
  }
}
