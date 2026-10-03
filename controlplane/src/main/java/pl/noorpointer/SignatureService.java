package pl.noorpointer;

import com.fasterxml.jackson.databind.JsonNode;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.HashSet;
import java.util.Map;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
class SignatureService {
    private final JdbcTemplate jdbc;
    private final Documents documents;

    SignatureService(JdbcTemplate jdbc, Documents documents) { this.jdbc = jdbc; this.documents = documents; }

    Map<String, Object> feed() {
        return Map.of("signatures", jdbc.query("SELECT document FROM signature ORDER BY id", (rs, row) -> documents.read(rs.getString(1))));
    }

    @Transactional
    public Map<String, Object> replace(String text) {
        JsonNode node = documents.parse(text);
        documents.validate("signatures", node);
        var ids = new HashSet<String>();
        for (JsonNode signature : node.path("signatures")) {
            if (!ids.add(signature.path("id").asText())) throw new IllegalArgumentException("Duplicate signature ID");
        }
        jdbc.update("DELETE FROM signature");
        Timestamp now = Timestamp.from(Instant.now());
        for (JsonNode signature : node.path("signatures")) {
            jdbc.update("INSERT INTO signature(id, document, imported_at) VALUES(?, ?, ?)", signature.path("id").asText(), documents.write(signature), now);
        }
        return Map.of("imported", ids.size());
    }
}
