package pl.noorpointer.web;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Arrays;
import java.util.HexFormat;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import pl.noorpointer.document.DocumentService;

@Component
public class CachedResponses {
  private final DocumentService documents;

  public CachedResponses(DocumentService documents) {
    this.documents = documents;
  }

  public <T> ResponseEntity<T> of(T value, String previous) {
    try {
      String tag =
          "\""
              + HexFormat.of()
                  .formatHex(
                      MessageDigest.getInstance("SHA-256")
                          .digest(documents.write(value).getBytes(StandardCharsets.UTF_8)))
              + "\"";
      if (previous != null
          && Arrays.stream(previous.split(","))
              .map(String::trim)
              .anyMatch(item -> item.equals(tag) || item.equals("W/" + tag) || item.equals("*"))) {
        return ResponseEntity.status(HttpStatus.NOT_MODIFIED)
            .eTag(tag)
            .header("Cache-Control", "private, no-cache")
            .build();
      }
      return ResponseEntity.ok().eTag(tag).header("Cache-Control", "private, no-cache").body(value);
    } catch (NoSuchAlgorithmException error) {
      throw new IllegalStateException(error);
    }
  }
}
