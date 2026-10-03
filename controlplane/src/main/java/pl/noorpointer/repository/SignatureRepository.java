package pl.noorpointer.repository;

import com.fasterxml.jackson.databind.JsonNode;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import pl.noorpointer.document.DocumentService;

@Repository
public class SignatureRepository {
  private final JdbcTemplate jdbc;
  private final DocumentService documents;

  public SignatureRepository(JdbcTemplate jdbc, DocumentService documents) {
    this.jdbc = jdbc;
    this.documents = documents;
  }

  public List<JsonNode> findAll() {
    return jdbc.query(
        "SELECT document FROM signature ORDER BY id", (rs, row) -> documents.read(rs.getString(1)));
  }

  public Optional<JsonNode> findById(String id) {
    return jdbc
        .query(
            "SELECT document FROM signature WHERE id = ?",
            (rs, row) -> documents.read(rs.getString(1)),
            id)
        .stream()
        .findFirst();
  }

  public void lockForWrite() {
    jdbc.execute("LOCK TABLE signature IN SHARE ROW EXCLUSIVE MODE");
  }

  public long count() {
    return jdbc.queryForObject("SELECT COUNT(*) FROM signature", Long.class);
  }

  public void insert(JsonNode signature) {
    jdbc.update(
        "INSERT INTO signature(id, document, imported_at) VALUES(?, ?, ?)",
        signature.path("id").asText(),
        documents.write(signature),
        Timestamp.from(Instant.now()));
  }

  public void replaceAll(List<JsonNode> signatures) {
    jdbc.update("DELETE FROM signature");
    Timestamp now = Timestamp.from(Instant.now());
    for (JsonNode signature : signatures) {
      jdbc.update(
          "INSERT INTO signature(id, document, imported_at) VALUES(?, ?, ?)",
          signature.path("id").asText(),
          documents.write(signature),
          now);
    }
  }
}
