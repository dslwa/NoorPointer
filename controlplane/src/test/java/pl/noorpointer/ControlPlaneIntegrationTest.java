package pl.noorpointer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import java.time.Instant;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import pl.noorpointer.document.DocumentService;

@SpringBootTest(
    properties = {
      "spring.datasource.url=${TEST_DATABASE_URL:jdbc:postgresql://localhost:5432/noorpointer_test?currentSchema=controlplane_test}",
      "spring.datasource.username=${TEST_DATABASE_USER:noor}",
      "spring.datasource.password=${TEST_DATABASE_PASSWORD:noorpass}",
      "spring.flyway.schemas=controlplane_test",
      "spring.flyway.default-schema=controlplane_test",
      "control-plane.admin-token=test-admin",
      "control-plane.gateway-token=test-gateway"
    })
@AutoConfigureMockMvc
class ControlPlaneIntegrationTest {
  @Autowired MockMvc mvc;
  @Autowired ObjectMapper mapper;
  @Autowired JdbcTemplate jdbc;
  @Autowired DocumentService documents;
  private static final String ADMIN = "Bearer test-admin", GATEWAY = "Bearer test-gateway";

  @BeforeEach
  void reset() {
    jdbc.update("DELETE FROM audit_event");
    jdbc.update("DELETE FROM signature");
    jdbc.update("UPDATE active_policy SET revision_id = 2 WHERE id = 1");
    jdbc.update("DELETE FROM policy_revision WHERE id > 3");
  }

  @Test
  void staticDashboardAndHealthArePublicButDataRequiresAdmin() throws Exception {
    mvc.perform(get("/")).andExpect(status().isOk()).andExpect(forwardedUrl("index.html"));
    String index =
        mvc.perform(get("/index.html"))
            .andExpect(status().isOk())
            .andExpect(content().string(org.hamcrest.Matchers.containsString("NoorPointer")))
            .andReturn()
            .getResponse()
            .getContentAsString();
    var assets =
        java.util.regex.Pattern.compile("(?:src|href)=\"(/assets/[^\"]+)\"").matcher(index);
    int assetCount = 0;
    while (assets.find()) {
      mvc.perform(get(assets.group(1))).andExpect(status().isOk());
      assetCount++;
    }
    assertThat(assetCount).isGreaterThanOrEqualTo(2);
    mvc.perform(get("/actuator/health"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.status").value("UP"));
    mvc.perform(get("/api/v1/dashboard")).andExpect(status().isUnauthorized());
    mvc.perform(get("/api/v1/dashboard").header("Authorization", GATEWAY))
        .andExpect(status().isForbidden());
    mvc.perform(
            put("/api/v1/active-policy")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"version\":2}")
                .header("Authorization", GATEWAY))
        .andExpect(status().isForbidden());
    mvc.perform(get("/api/gateway/policy").header("Authorization", GATEWAY))
        .andExpect(status().isOk());
  }

  @Test
  void seedsThreeProfilesAndEmptyStatistics() throws Exception {
    mvc.perform(get("/api/v1/policy-revisions").header("Authorization", ADMIN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(3));
    mvc.perform(get("/api/v1/dashboard").header("Authorization", ADMIN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.active_policy.revision.name").value("balanced"))
        .andExpect(jsonPath("$.summary.requests").value(0))
        .andExpect(jsonPath("$.budgets.length()").value(3));
  }

  @Test
  void creatingDraftDoesNotActivateItAndPublishingChangesGatewayEtag() throws Exception {
    MvcResult before =
        mvc.perform(get("/api/gateway/policy").header("Authorization", GATEWAY))
            .andExpect(status().isOk())
            .andReturn();
    String etag = before.getResponse().getHeader("ETag");
    var document = (ObjectNode) documents.profile("strict");
    document.withObject("/controls/prompt_injection").put("threshold", 0.7);
    JsonNode revision =
        json(
            mvc.perform(
                    post("/api/v1/policy-revisions")
                        .header("Authorization", ADMIN)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(
                            mapper.writeValueAsString(
                                Map.of("name", "strict-new", "document", document.toString()))))
                .andExpect(status().isCreated())
                .andReturn());
    mvc.perform(
            get("/api/gateway/policy")
                .header("Authorization", GATEWAY)
                .header("If-None-Match", etag))
        .andExpect(status().isNotModified());
    long version = revision.path("version").asLong();
    mvc.perform(
            put("/api/v1/active-policy")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"version\":" + version + "}")
                .header("Authorization", ADMIN))
        .andExpect(status().isOk());
    MvcResult after =
        mvc.perform(
                get("/api/gateway/policy")
                    .header("Authorization", GATEWAY)
                    .header("If-None-Match", etag))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.version").value(version))
            .andExpect(jsonPath("$.controls.prompt_injection.threshold").value(0.7))
            .andReturn();
    assertThat(after.getResponse().getHeader("ETag")).isNotEqualTo(etag);
    mvc.perform(get("/api/v1/policy-revisions/2").header("Authorization", ADMIN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.document.controls.prompt_injection.threshold").value(0.85));
  }

  @Test
  void rejectsInvalidPolicyAndUnknownFieldsWithoutChangingPublishedVersion() throws Exception {
    ObjectNode document = (ObjectNode) documents.profile("balanced");
    document.withObject("/controls/prompt_injection").put("threshold", 1.5);
    mvc.perform(
            post("/api/v1/policy-revisions")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    mapper.writeValueAsString(
                        Map.of("name", "bad", "document", document.toString()))))
        .andExpect(status().isBadRequest());
    document.withObject("/controls/prompt_injection").put("threshold", 0.85);
    document.put("typo", true);
    mvc.perform(
            post("/api/v1/policy-validations")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("document", document.toString()))))
        .andExpect(status().isBadRequest());
    mvc.perform(
            put("/api/v1/active-policy")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"version\":99999}")
                .header("Authorization", ADMIN))
        .andExpect(status().isNotFound());
    mvc.perform(get("/api/gateway/policy").header("Authorization", GATEWAY))
        .andExpect(jsonPath("$.version").value(2));
  }

  @Test
  void acceptsYamlPolicy() throws Exception {
    String yaml =
        """
        defaults:
          mode: monitor
          semantic_timeout_ms: 300
          on_semantic_timeout: fail_open
        models:
          allowed: [llama3.1:8b]
        controls:
          secrets: {enabled: true, action: monitor}
        """;
    mvc.perform(
            post("/api/v1/policy-revisions")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("name", "yaml", "document", yaml))))
        .andExpect(status().isCreated());
  }

  @Test
  void duplicateEventsAreIdempotentAndUsageIsCountedOnce() throws Exception {
    ObjectNode decision = event("decision-1", "decision", "block");
    decision.put("category", "LLM01:2025");
    ingest(decision).andExpect(jsonPath("$.accepted").value(true));
    ingest(decision).andExpect(jsonPath("$.accepted").value(false));
    ObjectNode usage = event("usage-1", "usage", "allow");
    usage.put("tokens", 130);
    usage.put("cost_usd", 0.025);
    usage.put("gpu_seconds", 2.5);
    usage.put("model", "local/llama");
    ingest(usage).andExpect(jsonPath("$.accepted").value(true));
    ingest(usage).andExpect(jsonPath("$.accepted").value(false));
    JsonNode stats =
        json(
            mvc.perform(get("/api/v1/dashboard").header("Authorization", ADMIN))
                .andExpect(status().isOk())
                .andReturn());
    assertThat(stats.path("summary").path("requests").asLong()).isEqualTo(1);
    assertThat(stats.path("summary").path("blocked").asLong()).isEqualTo(1);
    assertThat(stats.path("summary").path("tokens").asLong()).isEqualTo(130);
    assertThat(stats.path("summary").path("cost_usd").decimalValue()).isEqualByComparingTo("0.025");
    assertThat(stats.path("budgets").get(1).path("used").asLong()).isEqualTo(130);
    assertThat(stats.path("budgets").get(2).path("used").decimalValue())
        .isEqualByComparingTo("2.5");
  }

  @Test
  void invalidEventsAreRejectedAndDecisionsCannotDoubleCountUsage() throws Exception {
    ObjectNode invalid = event("bad", "decision", "block");
    invalid.put("occurred_at", "not-a-date");
    send(invalid).andExpect(status().isBadRequest());
    invalid.put("occurred_at", Instant.now().plusSeconds(3600).toString());
    send(invalid).andExpect(status().isBadRequest());
    invalid.put("occurred_at", Instant.now().toString());
    invalid.put("tokens", -3);
    send(invalid).andExpect(status().isBadRequest());
    invalid.put("tokens", 3);
    send(invalid).andExpect(status().isBadRequest());
    invalid.put("tokens", 0);
    invalid.put("action", "unexpected");
    send(invalid).andExpect(status().isBadRequest());
  }

  @Test
  void filtersPaginationAndEventDetailWork() throws Exception {
    ingest(event("blocked", "decision", "block"));
    ingest(event("allowed", "decision", "allow"));
    mvc.perform(
            get("/api/v1/audit-events")
                .header("Authorization", ADMIN)
                .param("action", "block")
                .param("agent", "finance-agent"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.total").value(1))
        .andExpect(jsonPath("$.items[0].id").value("blocked"));
    mvc.perform(
            get("/api/v1/audit-events")
                .header("Authorization", ADMIN)
                .param("size", "1")
                .param("page", "1"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items.length()").value(1))
        .andExpect(jsonPath("$.total").value(2));
    mvc.perform(get("/api/v1/audit-events/blocked").header("Authorization", ADMIN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.agent_id").value("finance-agent"));
    mvc.perform(get("/api/v1/audit-events").header("Authorization", ADMIN).param("size", "1000"))
        .andExpect(status().isBadRequest());
    mvc.perform(
            get("/api/v1/audit-events")
                .header("Authorization", ADMIN)
                .param("from", "2026-01-02T00:00:00Z")
                .param("to", "2026-01-01T00:00:00Z"))
        .andExpect(status().isBadRequest());
  }

  @Test
  void exportsRespectFiltersAndEscapeCsvAndCef() throws Exception {
    ObjectNode blocked = event("blocked", "decision", "block");
    blocked.put("message", "=SUM(1,2)\nline=two");
    blocked.put("control", "test|control");
    ingest(blocked);
    ingest(event("allowed", "decision", "allow"));
    mvc.perform(
            get("/api/v1/audit-events/export")
                .header("Authorization", ADMIN)
                .param("action", "block"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.length()").value(1));
    String csv =
        mvc.perform(
                get("/api/v1/audit-events/export")
                    .header("Authorization", ADMIN)
                    .param("format", "csv"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    assertThat(csv).contains("\"'=SUM(1,2)").contains("id,occurred_at");
    String cef =
        mvc.perform(
                get("/api/v1/audit-events/export")
                    .header("Authorization", ADMIN)
                    .param("format", "cef")
                    .param("action", "block"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();
    assertThat(cef).contains("test\\|control").contains("msg=\\=SUM(1,2)\\nline\\=two");
    assertThat(cef.lines().count()).isEqualTo(1);
  }

  @Test
  void signatureImportIsAtomicAndChangesGatewayEtag() throws Exception {
    String feed =
        """
{"signatures":[{"id":"DEMO-1","name":"Example","source":"https://example.org/attack",
"category":"LLM01:2025","action":"block","target":"prompt","match":{"type":"literal","value":"ignore previous"}}]}
""";
    String etag =
        mvc.perform(get("/api/gateway/signatures").header("Authorization", GATEWAY))
            .andReturn()
            .getResponse()
            .getHeader("ETag");
    mvc.perform(
            put("/api/v1/signature-feed")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("document", feed))))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.signatures.length()").value(1));
    mvc.perform(
            get("/api/gateway/signatures")
                .header("Authorization", GATEWAY)
                .header("If-None-Match", etag))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.signatures[0].id").value("DEMO-1"));
    var invalid = (ObjectNode) mapper.readTree(feed);
    invalid.withArray("signatures").add(invalid.withArray("signatures").get(0).deepCopy());
    mvc.perform(
            put("/api/v1/signature-feed")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("document", invalid.toString()))))
        .andExpect(status().isBadRequest());
    mvc.perform(get("/api/v1/signature-feed").header("Authorization", ADMIN))
        .andExpect(jsonPath("$.signatures.length()").value(1));
  }

  @Test
  void demoProducesExplicitlyMarkedEvents() throws Exception {
    mvc.perform(post("/api/v1/demo-batches").header("Authorization", ADMIN))
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.synthetic").value(true));
    mvc.perform(get("/api/v1/audit-events").header("Authorization", ADMIN))
        .andExpect(jsonPath("$.items[0].context.demo").value(true));
    mvc.perform(get("/api/v1/dashboard").header("Authorization", ADMIN))
        .andExpect(jsonPath("$.summary.requests").value(18));
  }

  @Test
  void repositoryGatewayEventsAreAuthenticatedMappedAndVisibleInDashboard() throws Exception {
    String payload =
        """
{"request_id":"go-request-1","agent_id":"go-agent","timestamp":"%s",
"action":"BLOCKED","reason":"PROMPT_INJECTION_DETECTED","owasp_category":"LLM01: Prompt Injection",
"prompt_snippet":"never persist this raw secret"}
"""
            .formatted(Instant.now());
    mvc.perform(
            post("/api/v1/audit/events").contentType(MediaType.APPLICATION_JSON).content(payload))
        .andExpect(status().isUnauthorized());
    mvc.perform(
            post("/api/v1/audit/events")
                .header("Authorization", GATEWAY)
                .contentType(MediaType.APPLICATION_JSON)
                .content(payload))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.accepted").value(true));
    mvc.perform(
            post("/api/v1/audit/events")
                .header("Authorization", GATEWAY)
                .contentType(MediaType.APPLICATION_JSON)
                .content(payload))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.accepted").value(false));
    mvc.perform(get("/api/v1/audit-events").header("Authorization", ADMIN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.total").value(1))
        .andExpect(jsonPath("$.items[0].action").value("block"))
        .andExpect(jsonPath("$.items[0].control").value("prompt_injection"))
        .andExpect(
            content()
                .string(
                    org.hamcrest.Matchers.not(
                        org.hamcrest.Matchers.containsString("never persist this raw secret"))));
    mvc.perform(get("/api/v1/audit/export").param("format", "cef").header("Authorization", ADMIN))
        .andExpect(status().isOk())
        .andExpect(content().string(org.hamcrest.Matchers.containsString("CEF:0|NoorPointer")));
    mvc.perform(get("/api/v1/audit/export").header("Authorization", GATEWAY))
        .andExpect(status().isForbidden());
  }

  @Test
  void legacyUsageIsCountedOnceAndInvalidUsageDoesNotWriteDecision() throws Exception {
    ObjectNode payload = mapper.createObjectNode();
    payload.put("request_id", "usage-from-go");
    payload.put("agent_id", "go-agent");
    payload.put("action", "ALLOWED");
    payload.put("timestamp", Instant.now().toString());
    payload.set(
        "token_usage",
        mapper.readTree("{\"prompt_tokens\":30,\"completion_tokens\":70,\"cost_usd\":0.01}"));
    for (int i = 0; i < 2; i++)
      mvc.perform(
              post("/api/v1/audit/events")
                  .header("Authorization", GATEWAY)
                  .contentType(MediaType.APPLICATION_JSON)
                  .content(payload.toString()))
          .andExpect(status().isOk());
    mvc.perform(get("/api/v1/dashboard").header("Authorization", ADMIN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.summary.requests").value(1))
        .andExpect(jsonPath("$.summary.tokens").value(100));
    payload.put("request_id", "bad-go-usage");
    payload.withObject("/token_usage").put("cost_usd", "bad");
    mvc.perform(
            post("/api/v1/audit/events")
                .header("Authorization", GATEWAY)
                .contentType(MediaType.APPLICATION_JSON)
                .content(payload.toString()))
        .andExpect(status().isBadRequest());
    mvc.perform(get("/api/v1/audit-events").header("Authorization", ADMIN))
        .andExpect(jsonPath("$.total").value(2));
  }

  @Test
  void canonicalAuditCreationReturnsLocationAndRetriesPreserveOriginalEvent() throws Exception {
    ObjectNode first = event("canonical-event", "decision", "block");
    MvcResult created =
        mvc.perform(
                post("/api/v1/audit-events")
                    .header("Authorization", GATEWAY)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(first.toString()))
            .andExpect(status().isCreated())
            .andExpect(header().string("Location", "/api/v1/audit-events/canonical-event"))
            .andExpect(jsonPath("$.accepted").value(true))
            .andReturn();
    String location = created.getResponse().getHeader("Location");
    first.put("action", "allow");
    mvc.perform(
            post("/api/v1/audit-events")
                .header("Authorization", GATEWAY)
                .contentType(MediaType.APPLICATION_JSON)
                .content(first.toString()))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.accepted").value(false));
    mvc.perform(get(location).header("Authorization", ADMIN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.action").value("block"));
    mvc.perform(get(location).header("Authorization", GATEWAY)).andExpect(status().isForbidden());
  }

  @Test
  void publishingTheSameVersionIsIdempotentAndGatewayAccessIsReadOnly() throws Exception {
    MvcResult first =
        mvc.perform(
                put("/api/v1/active-policy")
                    .header("Authorization", ADMIN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"version\":1}"))
            .andExpect(status().isOk())
            .andReturn();
    mvc.perform(
            put("/api/v1/active-policy")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"version\":1}"))
        .andExpect(status().isOk())
        .andExpect(content().json(first.getResponse().getContentAsString()));
    mvc.perform(get("/api/v1/active-policy/document").header("Authorization", GATEWAY))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.version").value(1));
    mvc.perform(get("/api/v1/signature-feed").header("Authorization", GATEWAY))
        .andExpect(status().isOk());
    mvc.perform(get("/api/v1/schemas/policy").header("Authorization", GATEWAY))
        .andExpect(status().isOk());
    mvc.perform(
            put("/api/v1/signature-feed")
                .header("Authorization", GATEWAY)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"document\":\"{\\\"signatures\\\":[]}\"}"))
        .andExpect(status().isForbidden());
    mvc.perform(get("/api/v1/active-policy").header("Authorization", GATEWAY))
        .andExpect(status().isForbidden());
    mvc.perform(get("/api/v1/audit-events/export").header("Authorization", GATEWAY))
        .andExpect(status().isForbidden());
  }

  @Test
  void restErrorsHaveConsistentStatusMessagePathAndTimestamp() throws Exception {
    for (String value : new String[] {"0", "-1"}) {
      mvc.perform(
              put("/api/v1/active-policy")
                  .header("Authorization", ADMIN)
                  .contentType(MediaType.APPLICATION_JSON)
                  .content("{\"version\":" + value + "}"))
          .andExpect(status().isBadRequest())
          .andExpect(jsonPath("$.status").value(400))
          .andExpect(jsonPath("$.message").isNotEmpty())
          .andExpect(jsonPath("$.path").value("/api/v1/active-policy"))
          .andExpect(jsonPath("$.timestamp").isNotEmpty());
    }
    mvc.perform(
            get("/api/v1/audit-events")
                .header("Authorization", ADMIN)
                .param("from", "invalid-date"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.status").value(400));
    mvc.perform(
            get("/api/v1/audit-events")
                .header("Authorization", ADMIN)
                .param("page", "not-a-number"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.status").value(400));
    mvc.perform(get("/api/v1/policy-profiles/missing").header("Authorization", ADMIN))
        .andExpect(status().isNotFound())
        .andExpect(jsonPath("$.status").value(404));
    mvc.perform(delete("/api/v1/active-policy").header("Authorization", ADMIN))
        .andExpect(status().isMethodNotAllowed())
        .andExpect(header().exists("Allow"))
        .andExpect(jsonPath("$.status").value(405));
    mvc.perform(get("/api/v1/dashboard"))
        .andExpect(status().isUnauthorized())
        .andExpect(jsonPath("$.status").value(401))
        .andExpect(jsonPath("$.path").value("/api/v1/dashboard"));
  }

  @Test
  void policyRevisionCreationHasRetrievableLocationAndImmutableDocument() throws Exception {
    String body =
        mapper.writeValueAsString(
            Map.of("name", "rest-draft", "document", documents.profile("strict").toString()));
    MvcResult created =
        mvc.perform(
                post("/api/v1/policy-revisions")
                    .header("Authorization", ADMIN)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body))
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andReturn();
    String location = created.getResponse().getHeader("Location");
    mvc.perform(get(location).header("Authorization", ADMIN))
        .andExpect(status().isOk())
        .andExpect(content().json(created.getResponse().getContentAsString()));
    mvc.perform(
            put(location)
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(body))
        .andExpect(status().isMethodNotAllowed());
  }

  private ObjectNode event(String id, String kind, String action) {
    var node = mapper.createObjectNode();
    node.put("id", id);
    node.put("kind", kind);
    node.put("action", action);
    node.put("occurred_at", Instant.now().toString());
    node.put("agent_id", "finance-agent");
    node.put("team", "finance");
    node.put("model", "llama3.1:8b");
    return node;
  }

  private org.springframework.test.web.servlet.ResultActions send(JsonNode node) throws Exception {
    return mvc.perform(
        post("/api/gateway/events")
            .header("Authorization", GATEWAY)
            .contentType(MediaType.APPLICATION_JSON)
            .content(node.toString()));
  }

  private org.springframework.test.web.servlet.ResultActions ingest(JsonNode node)
      throws Exception {
    return send(node).andExpect(status().isOk());
  }

  private JsonNode json(MvcResult result) throws Exception {
    return mapper.readTree(result.getResponse().getContentAsString());
  }
}
