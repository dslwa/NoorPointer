package pl.noorpointer;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.math.BigDecimal;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Timestamp;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
class AuditService {
    record Filter(String action, String category, String agent, Instant from, Instant to) {}
    private record Query(String sql, List<Object> args) {}
    private final JdbcTemplate jdbc;
    private final Documents documents;

    AuditService(JdbcTemplate jdbc, Documents documents) { this.jdbc = jdbc; this.documents = documents; }

    Map<String, Object> ingest(JsonNode input) {
        documents.validate("audit", input);
        Instant occurred;
        try { occurred = Instant.parse(input.path("occurred_at").asText()); }
        catch (Exception e) { throw new IllegalArgumentException("occurred_at must be an ISO-8601 UTC timestamp"); }
        if (occurred.isAfter(Instant.now().plusSeconds(300))) throw new IllegalArgumentException("Event timestamp is too far in the future");
        if (!input.path("tokens").isMissingNode() && !input.path("tokens").canConvertToLong()) throw new IllegalArgumentException("tokens is too large");
        if (documents.write(input.path("context")).length() > 16000) throw new IllegalArgumentException("Event context is too large");
        // Usage is reported once per completed request; decision events never contribute spend.
        if (input.path("kind").asText().equals("decision") &&
            (input.path("tokens").asLong() != 0 || input.path("cost_usd").decimalValue().signum() != 0 || input.path("gpu_seconds").decimalValue().signum() != 0)) {
            throw new IllegalArgumentException("Report tokens, cost and GPU usage in a separate usage event");
        }
        String id = input.path("id").asText();
        try {
            jdbc.update("""
                INSERT INTO audit_event(id, occurred_at, received_at, kind, request_id, agent_id, team, model,
                session_id, control_name, action, severity, category, signature_id, policy_version, tokens,
                cost_usd, gpu_seconds, latency_ms, message, context_json)
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, id, Timestamp.from(occurred), Timestamp.from(Instant.now()), input.path("kind").asText(),
                text(input,"request_id",""), input.path("agent_id").asText(), text(input,"team","unknown"), text(input,"model","unknown"),
                text(input,"session_id",""), text(input,"control","unknown"), input.path("action").asText(), text(input,"severity","info"),
                text(input,"category","unclassified"), text(input,"signature_id",""), input.has("policy_version") ? input.path("policy_version").asLong() : null,
                input.path("tokens").asLong(0), decimal(input,"cost_usd"), decimal(input,"gpu_seconds"), input.path("latency_ms").asDouble(0),
                text(input,"message",""), input.has("context") ? documents.write(input.path("context")) : "{}");
            return Map.of("id", id, "accepted", true);
        } catch (DuplicateKeyException e) {
            return Map.of("id", id, "accepted", false);
        }
    }

    Map<String, Object> list(Filter filter, int page, int size) {
        if (page < 0 || page > 100000 || size < 1 || size > 100) throw new IllegalArgumentException("Invalid page or size (1–100)");
        Query query = where(filter);
        Long total = jdbc.queryForObject("SELECT COUNT(*) FROM audit_event" + query.sql(), Long.class, query.args().toArray());
        var args = new ArrayList<>(query.args()); args.add(size); args.add(page * size);
        var items = jdbc.query("SELECT * FROM audit_event" + query.sql() + " ORDER BY occurred_at DESC, id DESC LIMIT ? OFFSET ?", this::row, args.toArray());
        return Map.of("items", items, "total", total, "page", page, "size", size);
    }

    JsonNode get(String id) {
        var rows = jdbc.query("SELECT * FROM audit_event WHERE id = ?", this::row, id);
        if (rows.isEmpty()) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Event not found");
        return rows.getFirst();
    }

    List<JsonNode> export(Filter filter) {
        Query query = where(filter);
        long count = jdbc.queryForObject("SELECT COUNT(*) FROM audit_event" + query.sql(), Long.class, query.args().toArray());
        if (count > 10000) throw new ResponseStatusException(HttpStatus.PAYLOAD_TOO_LARGE, "Export is limited to 10,000 events; narrow the date range");
        return jdbc.query("SELECT * FROM audit_event" + query.sql() + " ORDER BY occurred_at DESC, id DESC LIMIT 10000", this::row, query.args().toArray());
    }

    Map<String, Object> summary() {
        LocalDate today = LocalDate.now(ZoneOffset.UTC);
        Instant start = today.minusDays(6).atStartOfDay().toInstant(ZoneOffset.UTC);
        Instant end = today.plusDays(1).atStartOfDay().toInstant(ZoneOffset.UTC);
        Query query = where(new Filter(null,null,null,start,end));
        var rows = jdbc.query("SELECT * FROM audit_event" + query.sql(), this::row, query.args().toArray());
        long requests = 0, blocked = 0, redacted = 0, tokens = 0;
        BigDecimal cost = BigDecimal.ZERO;
        var categories = new LinkedHashMap<String, Long>();
        var trends = new LinkedHashMap<String, Map<String, Object>>();
        for (int i = 6; i >= 0; i--) trends.put(today.minusDays(i).toString(), new LinkedHashMap<>(Map.of("date", today.minusDays(i).toString(), "requests", 0L, "blocked", 0L)));
        for (JsonNode event : rows) {
            if (event.path("kind").asText().equals("usage")) {
                tokens += event.path("tokens").asLong();
                cost = cost.add(event.path("cost_usd").decimalValue());
                continue;
            }
            requests++;
            String date = Instant.parse(event.path("occurred_at").asText()).atOffset(ZoneOffset.UTC).toLocalDate().toString();
            var day = trends.get(date);
            day.put("requests", (Long) day.get("requests") + 1);
            if (event.path("action").asText().equals("block")) {
                blocked++;
                day.put("blocked", (Long) day.get("blocked") + 1);
                categories.merge(event.path("category").asText(), 1L, Long::sum);
            }
            if (event.path("action").asText().equals("redact")) redacted++;
        }
        return Map.of("requests",requests,"blocked",blocked,"redacted",redacted,"tokens",tokens,"cost_usd",cost,
            "categories",categories,"trend",trends.values(),"from",start,"to",end,"timezone","UTC");
    }

    List<Map<String,Object>> budgets(JsonNode policy) {
        var result = new ArrayList<Map<String,Object>>();
        Instant now = Instant.now();
        var date = now.atOffset(ZoneOffset.UTC).toLocalDate();
        for (JsonNode budget : policy.path("budgets")) {
            String subject = budget.path("subject").asText();
            var parts = subject.split(":",2);
            String column = switch(parts[0]) {case "team" -> "team"; case "agent" -> "agent_id"; case "model" -> "model"; default -> throw new IllegalArgumentException("Invalid budget subject");};
            String pattern = parts[1].replace("\\","\\\\").replace("%","\\%").replace("_","\\_").replace("*","%");
            for (String limit : new String[]{"monthly_usd","daily_tokens","gpu_seconds_per_hour"}) {
                if (!budget.has(limit)) continue;
                String metric = switch(limit) {case "monthly_usd" -> "cost_usd"; case "daily_tokens" -> "tokens"; default -> "gpu_seconds";};
                Instant from = switch(limit) {
                    case "monthly_usd" -> date.withDayOfMonth(1).atStartOfDay().toInstant(ZoneOffset.UTC);
                    case "daily_tokens" -> date.atStartOfDay().toInstant(ZoneOffset.UTC);
                    default -> now.minusSeconds(3600);
                };
                BigDecimal used = jdbc.queryForObject("SELECT COALESCE(SUM(" + metric + "), 0) FROM audit_event WHERE kind = 'usage' AND " + column + " LIKE ? ESCAPE '\\' AND occurred_at >= ? AND occurred_at <= ?", BigDecimal.class, pattern, Timestamp.from(from), Timestamp.from(now));
                result.add(Map.of("subject",subject,"metric",limit,"limit",budget.get(limit),"used",used,"on_exceed",budget.path("on_exceed").asText()));
            }
        }
        return result;
    }

    private Query where(Filter filter) {
        if (filter.from() != null && filter.to() != null && !filter.from().isBefore(filter.to())) throw new IllegalArgumentException("from must be before to");
        var conditions = new ArrayList<String>();
        var args = new ArrayList<Object>();
        if (filter.action() != null && !filter.action().isBlank()) {
            if (!Set.of("allow","block","redact","monitor","timeout").contains(filter.action())) throw new IllegalArgumentException("Unknown action");
            conditions.add("action = ?"); args.add(filter.action());
        }
        if (filter.category() != null && !filter.category().isBlank()) { conditions.add("category = ?"); args.add(filter.category()); }
        if (filter.agent() != null && !filter.agent().isBlank()) { conditions.add("agent_id = ?"); args.add(filter.agent()); }
        if (filter.from() != null) {conditions.add("occurred_at >= ?");args.add(Timestamp.from(filter.from()));}
        if (filter.to() != null) {conditions.add("occurred_at < ?");args.add(Timestamp.from(filter.to()));}
        return new Query(conditions.isEmpty() ? "" : " WHERE " + String.join(" AND ",conditions), args);
    }

    private JsonNode row(ResultSet rs, int index) throws SQLException {
        ObjectNode node = (ObjectNode) documents.read("{}");
        for (String name : new String[]{"id","kind","request_id","agent_id","team","model","session_id","action","severity","category","signature_id","message"}) node.put(name,rs.getString(name));
        node.put("control",rs.getString("control_name"));
        node.put("occurred_at",rs.getTimestamp("occurred_at").toInstant().toString());
        node.put("received_at",rs.getTimestamp("received_at").toInstant().toString());
        if (rs.getObject("policy_version") != null) node.put("policy_version",rs.getLong("policy_version"));
        node.put("tokens",rs.getLong("tokens"));node.put("cost_usd",rs.getBigDecimal("cost_usd"));
        node.put("gpu_seconds",rs.getBigDecimal("gpu_seconds"));node.put("latency_ms",rs.getDouble("latency_ms"));
        node.set("context",documents.read(rs.getString("context_json")));
        return node;
    }

    private static String text(JsonNode node, String key, String fallback) {return node.path(key).asText(fallback);}
    private static BigDecimal decimal(JsonNode node, String key) {return node.has(key) ? node.path(key).decimalValue() : BigDecimal.ZERO;}
}
