package pl.noorpointer;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.http.HttpStatus;

@Service
class PolicyService implements ApplicationRunner {
    record Draft(@NotBlank @Size(max=120) String name, @Size(max=1000) String description,
                 @NotBlank @Size(max=1_000_000) String document) {}
    record Revision(long version, String name, String description, Instant created_at, JsonNode document) {}

    private final JdbcTemplate jdbc;
    private final Documents documents;

    PolicyService(JdbcTemplate jdbc, Documents documents) { this.jdbc = jdbc; this.documents = documents; }

    @Override
    @Transactional
    public void run(ApplicationArguments args) {
        if (jdbc.queryForObject("SELECT COUNT(*) FROM policy_revision", Long.class) == 0) {
            long balanced = 0;
            for (String profile : new String[]{"permissive", "balanced", "strict"}) {
                var revision = create(new Draft(profile, "Built-in " + profile + " profile", documents.write(documents.profile(profile))));
                if (profile.equals("balanced")) balanced = revision.version();
            }
            jdbc.update("INSERT INTO active_policy(id, revision_id, published_at) VALUES(1, ?, ?)", balanced, Timestamp.from(Instant.now()));
        }
    }

    @Transactional
    public Revision create(Draft draft) {
        JsonNode node = documents.parse(draft.document());
        documents.validate("policy", node);
        Instant now = Instant.now();
        var keys = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            var statement = connection.prepareStatement("INSERT INTO policy_revision(name, description, document, created_at) VALUES(?, ?, ?, ?)", new String[]{"id"});
            statement.setString(1, draft.name().trim());
            statement.setString(2, draft.description() == null ? "" : draft.description());
            statement.setString(3, documents.write(node));
            statement.setTimestamp(4, Timestamp.from(now));
            return statement;
        }, keys);
        long id = java.util.Objects.requireNonNull(keys.getKey()).longValue();
        ((ObjectNode) node).put("version", id);
        jdbc.update("UPDATE policy_revision SET document = ? WHERE id = ?", documents.write(node), id);
        return get(id);
    }

    List<Revision> list() {
        return jdbc.query("SELECT * FROM policy_revision ORDER BY id DESC", (rs, row) -> new Revision(rs.getLong("id"), rs.getString("name"), rs.getString("description"), rs.getTimestamp("created_at").toInstant(), documents.read(rs.getString("document"))));
    }

    Revision get(long id) {
        var rows = jdbc.query("SELECT * FROM policy_revision WHERE id = ?", (rs, row) -> new Revision(rs.getLong("id"), rs.getString("name"), rs.getString("description"), rs.getTimestamp("created_at").toInstant(), documents.read(rs.getString("document"))), id);
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Policy revision not found");
        return rows.getFirst();
    }

    Map<String, Object> active() {
        var rows = jdbc.queryForList("SELECT revision_id, published_at FROM active_policy WHERE id = 1");
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE, "No policy published");
        long version = ((Number) rows.getFirst().get("revision_id")).longValue();
        return Map.of("revision", get(version), "published_at", rows.getFirst().get("published_at").toString());
    }

    @Transactional
    public Map<String, Object> publish(long version) {
        get(version);
        jdbc.update("UPDATE active_policy SET revision_id = ?, published_at = ?, lock_version = lock_version + 1 WHERE id = 1", version, Timestamp.from(Instant.now()));
        return active();
    }

    JsonNode gatewayPolicy() { return ((Revision) active().get("revision")).document(); }
}
