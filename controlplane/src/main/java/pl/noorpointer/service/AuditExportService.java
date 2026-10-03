package pl.noorpointer.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.util.List;
import org.springframework.stereotype.Service;
import pl.noorpointer.document.DocumentService;
import pl.noorpointer.dto.AuditExport;
import pl.noorpointer.dto.AuditFilter;

@Service
public class AuditExportService {
  private final AuditService audit;
  private final DocumentService documents;
  private final CefFormatter cef;

  public AuditExportService(AuditService audit, DocumentService documents, CefFormatter cef) {
    this.audit = audit;
    this.documents = documents;
    this.cef = cef;
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
      body = cef.format(events);
    }
    return new AuditExport(body, type, "noorpointer-events." + format);
  }

  static String csv(String value) {
    if (value.matches("(?s)^\\s*[=+@-].*")) value = "'" + value;
    return "\"" + value.replace("\"", "\"\"") + "\"";
  }
}
