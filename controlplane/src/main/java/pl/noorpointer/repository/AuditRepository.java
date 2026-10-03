package pl.noorpointer.repository;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.Set;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;
import pl.noorpointer.document.DocumentService;
import pl.noorpointer.dto.AuditFilter;
import pl.noorpointer.dto.PageResponse;

@Repository
public class AuditRepository {
  private record Query(String sql, List<Object> args) {}

  private final JdbcTemplate jdbc;
  private final DocumentService documents;

  public AuditRepository(JdbcTemplate jdbc, DocumentService documents) {
    this.jdbc = jdbc;
    this.documents = documents;
  }

  public boolean insert(JsonNode input, Instant occurred) {
    String id = input.path("id").asText();
    return jdbc.update(
            """
INSERT INTO audit_event(id, occurred_at, received_at, kind, request_id, agent_id, team, model,
session_id, control_name, action, severity, category, signature_id, policy_version, tokens,
cost_usd, gpu_seconds, latency_ms, message, context_json)
VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (id) DO NOTHING
""",
            id,
            Timestamp.from(occurred),
            Timestamp.from(Instant.now()),
            input.path("kind").asText(),
            text(input, "request_id", ""),
            input.path("agent_id").asText(),
            text(input, "team", "unknown"),
            text(input, "model", "unknown"),
            text(input, "session_id", ""),
            text(input, "control", "unknown"),
            input.path("action").asText(),
            text(input, "severity", "info"),
            text(input, "category", "unclassified"),
            text(input, "signature_id", ""),
            input.has("policy_version") ? input.path("policy_version").asLong() : null,
            input.path("tokens").asLong(0),
            decimal(input, "cost_usd"),
            decimal(input, "gpu_seconds"),
            input.path("latency_ms").asDouble(0),
            text(input, "message", ""),
            input.has("context") ? documents.write(input.path("context")) : "{}")
        > 0;
  }

  public long count(AuditFilter filter) {
    Query query = where(filter);
    return jdbc.queryForObject(
        "SELECT COUNT(*) FROM audit_event" + query.sql(), Long.class, query.args().toArray());
  }

  public PageResponse<JsonNode> findPage(AuditFilter filter, int page, int size) {
    Query query = where(filter);
    var args = new ArrayList<>(query.args());
    args.add(size);
    args.add(page * size);
    var rows =
        jdbc.query(
            "SELECT * FROM audit_event"
                + query.sql()
                + " ORDER BY occurred_at DESC, id DESC LIMIT ? OFFSET ?",
            this::row,
            args.toArray());
    return new PageResponse<>(rows, count(filter), page, size);
  }

  public Optional<JsonNode> findById(String id) {
    return jdbc.query("SELECT * FROM audit_event WHERE id = ?", this::row, id).stream().findFirst();
  }

  public List<JsonNode> findForExport(AuditFilter filter) {
    Query query = where(filter);
    return jdbc.query(
        "SELECT * FROM audit_event"
            + query.sql()
            + " ORDER BY occurred_at DESC, id DESC LIMIT 10000",
        this::row,
        query.args().toArray());
  }

  public List<JsonNode> findAll(AuditFilter filter) {
    Query query = where(filter);
    return jdbc.query("SELECT * FROM audit_event" + query.sql(), this::row, query.args().toArray());
  }

  public BigDecimal sumUsage(
      String metric, String column, String pattern, Instant from, Instant to) {
    if (!Set.of("cost_usd", "tokens", "gpu_seconds").contains(metric)
        || !Set.of("team", "agent_id", "model").contains(column)) {
      throw new IllegalArgumentException("Unknown usage metric or subject");
    }
    return jdbc.queryForObject(
        "SELECT COALESCE(SUM("
            + metric
            + "), 0) FROM audit_event WHERE kind = 'usage' AND "
            + column
            + " LIKE ? ESCAPE '\\' AND occurred_at >= ? AND occurred_at <= ?",
        BigDecimal.class,
        pattern,
        Timestamp.from(from),
        Timestamp.from(to));
  }

  private Query where(AuditFilter filter) {
    var conditions = new ArrayList<String>();
    var args = new ArrayList<Object>();
    if (filter.action() != null && !filter.action().isBlank()) {
      conditions.add("action = ?");
      args.add(filter.action());
    }
    if (filter.category() != null && !filter.category().isBlank()) {
      conditions.add("category = ?");
      args.add(filter.category());
    }
    if (filter.agent() != null && !filter.agent().isBlank()) {
      conditions.add("agent_id = ?");
      args.add(filter.agent());
    }
    if (filter.from() != null) {
      conditions.add("occurred_at >= ?");
      args.add(Timestamp.from(filter.from()));
    }
    if (filter.to() != null) {
      conditions.add("occurred_at < ?");
      args.add(Timestamp.from(filter.to()));
    }
    return new Query(
        conditions.isEmpty() ? "" : " WHERE " + String.join(" AND ", conditions), args);
  }

  private JsonNode row(ResultSet rs, int index) throws SQLException {
    ObjectNode node = (ObjectNode) documents.read("{}");
    for (String name :
        new String[] {
          "id",
          "kind",
          "request_id",
          "agent_id",
          "team",
          "model",
          "session_id",
          "action",
          "severity",
          "category",
          "signature_id",
          "message"
        }) node.put(name, rs.getString(name));
    node.put("control", rs.getString("control_name"));
    node.put("occurred_at", rs.getTimestamp("occurred_at").toInstant().toString());
    node.put("received_at", rs.getTimestamp("received_at").toInstant().toString());
    if (rs.getObject("policy_version") != null)
      node.put("policy_version", rs.getLong("policy_version"));
    node.put("tokens", rs.getLong("tokens"));
    node.put("cost_usd", rs.getBigDecimal("cost_usd"));
    node.put("gpu_seconds", rs.getBigDecimal("gpu_seconds"));
    node.put("latency_ms", rs.getDouble("latency_ms"));
    node.set("context", documents.read(rs.getString("context_json")));
    return node;
  }

  private static String text(JsonNode node, String key, String fallback) {
    return node.path(key).asText(fallback);
  }

  private static BigDecimal decimal(JsonNode node, String key) {
    return node.has(key) ? node.path(key).decimalValue() : BigDecimal.ZERO;
  }
}
