package pl.noorpointer.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.time.Instant;
import java.util.List;
import org.springframework.stereotype.Service;
import pl.noorpointer.document.DocumentService;
import pl.noorpointer.dto.AuditExport;
import pl.noorpointer.dto.AuditFilter;

@Service
public class AuditExportService {
  private final AuditService audit;
  private final DocumentService documents;

  public AuditExportService(AuditService audit, DocumentService documents) {
    this.audit = audit;
    this.documents = documents;
  }

  public AuditExport export(String format, AuditFilter filter) {
    if (!List.of("json", "csv", "cef").contains(format))
      throw new IllegalArgumentException("Supported formats: json, csv, cef");
    var events = audit.export(filter);
    String body;
    String type;
    if (format.equals("json")) {
      body = documents.write(events);
      type = "application/json";
    } else if (format.equals("csv")) {
      type = "text/csv;charset=UTF-8";
      var fields =
          List.of(
              "id",
              "occurred_at",
              "agent_id",
              "team",
              "model",
              "kind",
              "action",
              "severity",
              "control",
              "category",
              "signature_id",
              "tokens",
              "cost_usd",
              "message");
      var text = new StringBuilder(String.join(",", fields)).append('\n');
      for (JsonNode event : events)
        text.append(
                fields.stream()
                    .map(f -> csv(event.path(f).asText()))
                    .collect(java.util.stream.Collectors.joining(",")))
            .append('\n');
      body = text.toString();
    } else {
      type = "text/plain;charset=UTF-8";
      var text = new StringBuilder();
      for (JsonNode event : events)
        text.append("CEF:0|NoorPointer|ControlPlane|0.1|")
            .append(cefHeader(event.path("control").asText()))
            .append('|')
            .append(cefHeader(event.path("action").asText()))
            .append('|')
            .append(severity(event.path("severity").asText()))
            .append("|externalId=")
            .append(cefValue(event.path("id").asText()))
            .append(" rt=")
            .append(Instant.parse(event.path("occurred_at").asText()).toEpochMilli())
            .append(" suser=")
            .append(cefValue(event.path("agent_id").asText()))
            .append(" cat=")
            .append(cefValue(event.path("category").asText()))
            .append(" msg=")
            .append(cefValue(event.path("message").asText()))
            .append('\n');
      body = text.toString();
    }
    return new AuditExport(body, type, "noorpointer-events." + format);
  }

  static String csv(String value) {
    if (value.matches("(?s)^\\s*[=+@-].*")) value = "'" + value;
    return "\"" + value.replace("\"", "\"\"") + "\"";
  }

  private static String cefHeader(String value) {
    return value.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").replace("\r", " ");
  }

  private static String cefValue(String value) {
    return value
        .replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace("\n", "\\n")
        .replace("\r", "\\r");
  }

  private static int severity(String level) {
    return switch (level) {
      case "critical" -> 10;
      case "high" -> 8;
      case "medium" -> 5;
      case "low" -> 3;
      default -> 1;
    };
  }
}
