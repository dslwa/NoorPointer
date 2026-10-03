package pl.noorpointer.service;

import com.fasterxml.jackson.databind.JsonNode;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import org.springframework.stereotype.Component;

/** File-based CEF 0; dictionary fields and escaping follow the ArcSight CEF standard. */
@Component
public class CefFormatter {
  public String format(List<JsonNode> events) {
    var result = new StringBuilder();
    for (JsonNode event : events) {
      boolean usage = event.path("kind").asText().equals("usage");
      String control = event.path("control").asText("gateway");
      String eventClass = usage ? "USAGE" : event.path("signature_id").asText("");
      if (eventClass.isBlank()) {
        eventClass = control.isBlank() ? "GATEWAY_DECISION" : control.toUpperCase(Locale.ROOT);
      }
      result
          .append("CEF:0|NoorPointer|Gateway|0.1.0|")
          .append(header(eventClass))
          .append('|')
          .append(header(usage ? "LLM usage" : eventName(control)))
          .append('|')
          .append(severity(event.path("severity").asText()))
          .append('|');

      var fields = new StringBuilder();
      String id = event.path("id").asText();
      // externalId has a 40-character CEF limit. Preserve long IDs in flexString1.
      field(
          fields,
          "externalId",
          id.length() <= 40
              ? id
              : UUID.nameUUIDFromBytes(id.getBytes(StandardCharsets.UTF_8)).toString());
      field(fields, "act", action(event.path("action").asText()));
      field(fields, "cat", event.path("category").asText());
      field(fields, "end", epoch(event.path("occurred_at").asText()));
      field(fields, "rt", epoch(event.path("received_at").asText()));
      custom(fields, "cs1", "AgentId", event.path("agent_id").asText());
      custom(fields, "cs2", "Team", event.path("team").asText());
      custom(fields, "cs3", "Model", event.path("model").asText());
      custom(fields, "cs4", "RequestId", event.path("request_id").asText());
      custom(fields, "cs5", "SessionId", event.path("session_id").asText());
      custom(fields, "cs6", "Control", control);
      custom(fields, "flexString1", "EventId", id);
      custom(fields, "flexString2", "EventKind", event.path("kind").asText());
      custom(fields, "cn1", "Tokens", event.path("tokens").asText("0"));
      if (event.has("policy_version")) {
        custom(fields, "cn2", "PolicyVersion", event.path("policy_version").asText());
      }
      custom(fields, "cfp1", "CostUSD", event.path("cost_usd").asText("0"));
      custom(fields, "cfp2", "GPUSeconds", event.path("gpu_seconds").asText("0"));
      custom(fields, "cfp3", "LatencyMs", event.path("latency_ms").asText("0"));
      custom(
          fields,
          "flexNumber1",
          "Demo",
          event.path("context").path("demo").asBoolean() ? "1" : "0");
      // msg is limited to 1023 characters; JSON retains the full message and context.
      field(fields, "msg", limit(event.path("message").asText(), 1023));
      result.append(fields).append('\n');
    }
    return result.toString();
  }

  private static String eventName(String control) {
    return switch (control) {
      case "prompt_injection" -> "Prompt injection";
      case "secrets" -> "Secret leakage";
      case "pii_regex", "pii_ner" -> "Personal data exposure";
      case "content_safety" -> "Unsafe content";
      case "attack_signatures" -> "Attack signature match";
      case "agent_loops" -> "Agent loop";
      case "budgets" -> "Budget limit";
      case "mcp_tools" -> "MCP tool access";
      case "model_allowlist" -> "Model access";
      default -> "Gateway decision";
    };
  }

  private static String action(String action) {
    return switch (action) {
      case "allow" -> "ALLOWED";
      case "block" -> "BLOCKED";
      case "redact" -> "REDACTED";
      case "monitor" -> "MONITORED";
      case "timeout" -> "TIMEOUT";
      default -> action.toUpperCase(Locale.ROOT);
    };
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

  private static String epoch(String timestamp) {
    return Long.toString(Instant.parse(timestamp).toEpochMilli());
  }

  private static void custom(StringBuilder target, String key, String label, String value) {
    if (value.isBlank()) return;
    field(target, key + "Label", label);
    field(target, key, value);
  }

  private static void field(StringBuilder target, String key, String value) {
    if (value.isEmpty()) return;
    if (!target.isEmpty()) target.append(' ');
    target.append(key).append('=').append(extension(value));
  }

  private static String header(String value) {
    return value.replace("\\", "\\\\").replace("|", "\\|").replace('\n', ' ').replace('\r', ' ');
  }

  private static String extension(String value) {
    return value
        .replace("\\", "\\\\")
        .replace("=", "\\=")
        .replace("\n", "\\n")
        .replace("\r", "\\r");
  }

  private static String limit(String value, int maximum) {
    if (value.length() <= maximum) return value;
    int end = Character.isHighSurrogate(value.charAt(maximum - 1)) ? maximum - 1 : maximum;
    return value.substring(0, end);
  }
}
