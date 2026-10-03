package pl.noorpointer.repository;

import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Repository;
import pl.noorpointer.document.DocumentService;
import pl.noorpointer.dto.ActivePolicyResponse;
import pl.noorpointer.dto.PolicyRevisionResponse;

@Repository
public class PolicyRepository {
  private final JdbcTemplate jdbc;
  private final RowMapper<PolicyRevisionResponse> rowMapper;

  public PolicyRepository(JdbcTemplate jdbc, DocumentService documents) {
    this.jdbc = jdbc;
    this.rowMapper =
        (rs, row) ->
            new PolicyRevisionResponse(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getString("description"),
                rs.getTimestamp("created_at").toInstant(),
                documents.read(rs.getString("document")));
  }

  public boolean isEmpty() {
    return jdbc.queryForObject("SELECT COUNT(*) FROM policy_revision", Long.class) == 0;
  }

  public long insert(String name, String description, String document, Instant createdAt) {
    var keys = new GeneratedKeyHolder();
    jdbc.update(
        connection -> {
          var statement =
              connection.prepareStatement(
                  "INSERT INTO policy_revision(name, description, document, created_at) VALUES(?,"
                      + " ?, ?, ?)",
                  new String[] {"id"});
          statement.setString(1, name);
          statement.setString(2, description);
          statement.setString(3, document);
          statement.setTimestamp(4, Timestamp.from(createdAt));
          return statement;
        },
        keys);
    return Objects.requireNonNull(keys.getKey()).longValue();
  }

  public void updateDocument(long version, String document) {
    jdbc.update("UPDATE policy_revision SET document = ? WHERE id = ?", document, version);
  }

  public List<PolicyRevisionResponse> findAll() {
    return jdbc.query("SELECT * FROM policy_revision ORDER BY id DESC", rowMapper);
  }

  public Optional<PolicyRevisionResponse> findByVersion(long version) {
    return jdbc.query("SELECT * FROM policy_revision WHERE id = ?", rowMapper, version).stream()
        .findFirst();
  }

  public Optional<ActivePolicyResponse> findActive() {
    return jdbc
        .query(
            "SELECT p.*, a.published_at FROM active_policy a JOIN policy_revision p ON p.id ="
                + " a.revision_id WHERE a.id = 1",
            (rs, row) ->
                new ActivePolicyResponse(
                    rowMapper.mapRow(rs, row), rs.getTimestamp("published_at").toInstant()))
        .stream()
        .findFirst();
  }

  public void initializeActive(long version) {
    jdbc.update(
        "INSERT INTO active_policy(id, revision_id, published_at) VALUES(1, ?, ?)",
        version,
        Timestamp.from(Instant.now()));
  }

  public void publish(long version) {
    jdbc.update(
        "UPDATE active_policy SET revision_id = ?, published_at = ?, lock_version = lock_version +"
            + " 1 WHERE id = 1",
        version,
        Timestamp.from(Instant.now()));
  }
}
