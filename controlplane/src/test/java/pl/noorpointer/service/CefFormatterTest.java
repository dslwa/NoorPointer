package pl.noorpointer.service;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class CefFormatterTest {
  private final ObjectMapper mapper = new ObjectMapper();
  private final CefFormatter cef = new CefFormatter();

  @Test
  void matchesTheDocumentedCefExampleWithSecurityCorrelationFields() {
    assertThat(cef.format(List.of(event())))
        .isEqualTo(
            "CEF:0|NoorPointer|Gateway|0.1.0|PROMPT_INJECTION|Prompt"
                + " injection|8|externalId=event-001 act=BLOCKED cat=LLM01:2025 end=1767225600000"
                + " rt=1767225601000 cs1Label=AgentId cs1=agent-01 cs2Label=Team cs2=finance"
                + " cs3Label=Model cs3=llama3.1:8b cs4Label=RequestId cs4=request-001"
                + " cs5Label=SessionId cs5=session-001 cs6Label=Control cs6=prompt_injection"
                + " flexString1Label=EventId flexString1=event-001 flexString2Label=EventKind"
                + " flexString2=decision cn1Label=Tokens cn1=0 cn2Label=PolicyVersion cn2=3"
                + " cfp1Label=CostUSD cfp1=0.0 cfp2Label=GPUSeconds cfp2=0.0 cfp3Label=LatencyMs"
                + " cfp3=12.5 flexNumber1Label=Demo flexNumber1=0 msg=Prompt injection detected\n");
  }

  @Test
  void escapesHeaderAndExtensionsWithoutAllowingForgedFieldsOrRecords() {
    var event = event();
    event.put("signature_id", "RULE|\\attack\r\nnext");
    event.put("agent_id", "żółć |\\agent act=ALLOWED\r\nCEF:0|forged");
    event.put("request_id", "ends-with-pipe|");
    event.put("message", "=danger \\ path\nsecond\rthird msg=fake | still message");
    String text = cef.format(List.of(event));
    assertThat(text)
        .startsWith("CEF:0|NoorPointer|Gateway|0.1.0|RULE\\|\\\\attack  next|Prompt injection|8|")
        .contains("cs1=żółć |\\\\agent act\\=ALLOWED\\r\\nCEF:0|forged")
        .contains("cs4=ends-with-pipe| cs5Label=SessionId")
        .contains("msg=\\=danger \\\\ path\\nsecond\\rthird msg\\=fake | still message");
    assertThat(text.lines()).hasSize(1);
    assertThat(text.getBytes(StandardCharsets.UTF_8))
        .contains("żółć".getBytes(StandardCharsets.UTF_8));
  }

  @ParameterizedTest
  @CsvSource({"info,1", "low,3", "medium,5", "high,8", "critical,10"})
  void mapsSeverityToTheCefZeroToTenScale(String level, int value) {
    var event = event();
    event.put("severity", level);
    assertThat(cef.format(List.of(event))).contains("|Prompt injection|" + value + "|");
  }

  @Test
  void usageHasItsOwnEventClassAndNumericMetrics() {
    var event = event();
    event.put("kind", "usage");
    event.put("action", "allow");
    event.put("tokens", 12345678901L);
    event.put("cost_usd", 0.0125);
    event.put("gpu_seconds", 2.75);
    event.set("context", mapper.createObjectNode().put("demo", true));
    assertThat(cef.format(List.of(event)))
        .contains(
            "|USAGE|LLM usage|8|",
            "act=ALLOWED",
            "cn1=12345678901",
            "cfp1=0.0125",
            "cfp2=2.75",
            "flexNumber1=1");
  }

  @Test
  void preservesLongIdsAndHonorsMessageLengthWithoutCuttingUnicodeSurrogates() {
    var event = event();
    String id = "event-" + "x".repeat(90);
    event.put("id", id);
    event.put("message", "a".repeat(1022) + "🙂" + "z".repeat(50));
    String text = cef.format(List.of(event));
    String exportedId = text.substring(text.indexOf("externalId=") + 11, text.indexOf(" act="));
    assertThat(exportedId).hasSize(36);
    assertThat(text).contains("flexString1=" + id).endsWith("msg=" + "a".repeat(1022) + "\n");
    assertThat(cef.format(List.of(event))).isEqualTo(text);
  }

  @Test
  void omitsAbsentOptionalValuesAndReturnsAnEmptyFileWhenNoEventsMatch() {
    var event = event();
    for (String key : List.of("request_id", "session_id", "policy_version")) event.remove(key);
    assertThat(cef.format(List.of(event)))
        .doesNotContain("cs4Label", "cs5Label", "cn2Label", "null");
    assertThat(cef.format(List.of())).isEmpty();
  }

  private ObjectNode event() {
    var event = mapper.createObjectNode();
    event.put("id", "event-001");
    event.put("kind", "decision");
    event.put("action", "block");
    event.put("severity", "high");
    event.put("control", "prompt_injection");
    event.put("category", "LLM01:2025");
    event.put("occurred_at", "2026-01-01T00:00:00Z");
    event.put("received_at", "2026-01-01T00:00:01Z");
    event.put("agent_id", "agent-01");
    event.put("team", "finance");
    event.put("model", "llama3.1:8b");
    event.put("request_id", "request-001");
    event.put("session_id", "session-001");
    event.put("policy_version", 3);
    event.put("tokens", 0);
    event.put("cost_usd", 0.0);
    event.put("gpu_seconds", 0.0);
    event.put("latency_ms", 12.5);
    event.put("message", "Prompt injection detected");
    return event;
  }
}
