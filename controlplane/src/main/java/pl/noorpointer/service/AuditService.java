package pl.noorpointer.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;
import pl.noorpointer.document.DocumentService;
import pl.noorpointer.dto.AuditFilter;
import pl.noorpointer.dto.AuditReceipt;
import pl.noorpointer.dto.PageResponse;
import pl.noorpointer.repository.AuditRepository;

@Service
public class AuditService {
  private final AuditRepository repository;
  private final DocumentService documents;

  public AuditService(AuditRepository repository, DocumentService documents) {
    this.repository = repository;
    this.documents = documents;
  }

  public AuditReceipt ingest(JsonNode input) {
    documents.validate("audit", input);
    Instant occurred;
    try {
      occurred = Instant.parse(input.path("occurred_at").asText());
    } catch (Exception e) {
      throw new IllegalArgumentException("occurred_at must be an ISO-8601 UTC timestamp");
    }
    if (occurred.isAfter(Instant.now().plusSeconds(300)))
      throw new IllegalArgumentException("Event timestamp is too far in the future");
    if (!input.path("tokens").isMissingNode() && !input.path("tokens").canConvertToLong())
      throw new IllegalArgumentException("tokens is too large");
    if (documents.write(input.path("context")).length() > 16000)
      throw new IllegalArgumentException("Event context is too large");
    // Usage is reported once per completed request; decision events never contribute spend.
    if (input.path("kind").asText().equals("decision")
        && (input.path("tokens").asLong() != 0
            || input.path("cost_usd").decimalValue().signum() != 0
            || input.path("gpu_seconds").decimalValue().signum() != 0)) {
      throw new IllegalArgumentException(
          "Report tokens, cost and GPU usage in a separate usage event");
    }
    return new AuditReceipt(input.path("id").asText(), repository.insert(input, occurred));
  }

  public PageResponse<JsonNode> list(AuditFilter filter, int page, int size) {
    validateFilter(filter);
    if (page < 0 || page > 100000 || size < 1 || size > 100)
      throw new IllegalArgumentException("Invalid page or size (1–100)");
    return repository.findPage(filter, page, size);
  }

  public JsonNode get(String id) {
    return repository
        .findById(id)
        .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Event not found"));
  }

  public List<JsonNode> export(AuditFilter filter) {
    validateFilter(filter);
    if (repository.count(filter) > 10000)
      throw new ResponseStatusException(
          HttpStatus.PAYLOAD_TOO_LARGE,
          "Export is limited to 10,000 events; narrow the date range");
    return repository.findForExport(filter);
  }

  public Map<String, Object> summary() {
    LocalDate today = LocalDate.now(ZoneOffset.UTC);
    Instant start = today.minusDays(6).atStartOfDay().toInstant(ZoneOffset.UTC);
    Instant end = today.plusDays(1).atStartOfDay().toInstant(ZoneOffset.UTC);
    var rows = repository.findAll(new AuditFilter(null, null, null, start, end));
    long requests = 0, blocked = 0, redacted = 0, tokens = 0;
    BigDecimal cost = BigDecimal.ZERO;
    var categories = new LinkedHashMap<String, Long>();
    var trends = new LinkedHashMap<String, Map<String, Object>>();
    for (int i = 6; i >= 0; i--)
      trends.put(
          today.minusDays(i).toString(),
          new LinkedHashMap<>(
              Map.of("date", today.minusDays(i).toString(), "requests", 0L, "blocked", 0L)));
    for (JsonNode event : rows) {
      if (event.path("kind").asText().equals("usage")) {
        tokens += event.path("tokens").asLong();
        cost = cost.add(event.path("cost_usd").decimalValue());
        continue;
      }
      requests++;
      String date =
          Instant.parse(event.path("occurred_at").asText())
              .atOffset(ZoneOffset.UTC)
              .toLocalDate()
              .toString();
      var day = trends.get(date);
      day.put("requests", (Long) day.get("requests") + 1);
      if (event.path("action").asText().equals("block")) {
        blocked++;
        day.put("blocked", (Long) day.get("blocked") + 1);
        categories.merge(event.path("category").asText(), 1L, Long::sum);
      }
      if (event.path("action").asText().equals("redact")) redacted++;
    }
    return Map.of(
        "requests",
        requests,
        "blocked",
        blocked,
        "redacted",
        redacted,
        "tokens",
        tokens,
        "cost_usd",
        cost,
        "categories",
        categories,
        "trend",
        trends.values(),
        "from",
        start,
        "to",
        end,
        "timezone",
        "UTC");
  }

  public List<Map<String, Object>> budgets(JsonNode policy) {
    var result = new ArrayList<Map<String, Object>>();
    Instant now = Instant.now();
    var date = now.atOffset(ZoneOffset.UTC).toLocalDate();
    for (JsonNode budget : policy.path("budgets")) {
      String subject = budget.path("subject").asText();
      var parts = subject.split(":", 2);
      String column =
          switch (parts[0]) {
            case "team" -> "team";
            case "agent" -> "agent_id";
            case "model" -> "model";
            default -> throw new IllegalArgumentException("Invalid budget subject");
          };
      String pattern =
          parts[1].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_").replace("*", "%");
      for (String limit : new String[] {"monthly_usd", "daily_tokens", "gpu_seconds_per_hour"}) {
        if (!budget.has(limit)) continue;
        String metric =
            switch (limit) {
              case "monthly_usd" -> "cost_usd";
              case "daily_tokens" -> "tokens";
              default -> "gpu_seconds";
            };
        Instant from =
            switch (limit) {
              case "monthly_usd" -> date.withDayOfMonth(1).atStartOfDay().toInstant(ZoneOffset.UTC);
              case "daily_tokens" -> date.atStartOfDay().toInstant(ZoneOffset.UTC);
              default -> now.minusSeconds(3600);
            };
        BigDecimal used = repository.sumUsage(metric, column, pattern, from, now);
        result.add(
            Map.of(
                "subject",
                subject,
                "metric",
                limit,
                "limit",
                budget.get(limit),
                "used",
                used,
                "on_exceed",
                budget.path("on_exceed").asText()));
      }
    }
    return result;
  }

  private void validateFilter(AuditFilter filter) {
    if (filter.from() != null && filter.to() != null && !filter.from().isBefore(filter.to()))
      throw new IllegalArgumentException("from must be before to");
    if (filter.action() != null
        && !filter.action().isBlank()
        && !Set.of("allow", "block", "redact", "monitor", "timeout").contains(filter.action()))
      throw new IllegalArgumentException("Unknown action");
  }
}
