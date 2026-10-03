package pl.noorpointer;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import javax.sql.DataSource;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;

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
class SignatureIntegrationTest {
  private static final String ADMIN = "Bearer test-admin";
  @Autowired MockMvc mvc;
  @Autowired ObjectMapper mapper;
  @Autowired JdbcTemplate jdbc;
  @Autowired DataSource dataSource;

  @BeforeEach
  void reset() {
    jdbc.update("DELETE FROM signature");
  }

  @Test
  void addingRulesPreservesImportedFeedAndReturnsRetrievableResource() throws Exception {
    mvc.perform(
            put("/api/v1/signature-feed")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    mapper.writeValueAsString(
                        Map.of(
                            "document",
                            mapper.writeValueAsString(
                                Map.of("signatures", java.util.List.of(rule("EXISTING"))))))))
        .andExpect(status().isOk());
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(rule("NEW"))))
        .andExpect(status().isCreated())
        .andExpect(header().string("Location", "/api/v1/signatures/NEW"))
        .andExpect(jsonPath("$.id").value("NEW"));
    mvc.perform(get("/api/v1/signatures/NEW").header("Authorization", ADMIN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.match.value").value("reveal system instructions"));
    mvc.perform(get("/api/v1/signature-feed").header("Authorization", ADMIN))
        .andExpect(jsonPath("$.signatures.length()").value(2))
        .andExpect(jsonPath("$.signatures[0].id").value("EXISTING"));
  }

  @Test
  void invalidDuplicateAndUnauthorizedRequestsCannotChangeFeed() throws Exception {
    String rule = mapper.writeValueAsString(rule("ONE"));
    mvc.perform(post("/api/v1/signatures").contentType(MediaType.APPLICATION_JSON).content(rule))
        .andExpect(status().isUnauthorized());
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", "Bearer test-gateway")
                .contentType(MediaType.APPLICATION_JSON)
                .content(rule))
        .andExpect(status().isForbidden());
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(rule))
        .andExpect(status().isCreated());
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(rule))
        .andExpect(status().isConflict());
    var invalid = mapper.valueToTree(rule("INVALID"));
    ((com.fasterxml.jackson.databind.node.ObjectNode) invalid).put("action", "redact");
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(invalid.toString()))
        .andExpect(status().isBadRequest());
    mvc.perform(get("/api/v1/signatures/missing").header("Authorization", ADMIN))
        .andExpect(status().isNotFound());
    mvc.perform(get("/api/v1/signature-feed").header("Authorization", ADMIN))
        .andExpect(jsonPath("$.signatures.length()").value(1));
  }

  @Test
  void bundledStarterFeedCanBeImportedAndDefaultsToMonitoring() throws Exception {
    importDefaults()
        .andExpect(jsonPath("$.signatures.length()").value(7))
        .andExpect(
            jsonPath(
                "$.signatures[*].action",
                org.hamcrest.Matchers.everyItem(org.hamcrest.Matchers.is("monitor"))))
        .andExpect(
            jsonPath(
                "$.signatures[*].source",
                org.hamcrest.Matchers.everyItem(
                    org.hamcrest.Matchers.startsWith("https://genai.owasp.org/"))));
    mvc.perform(get("/api/v1/signature-feed").header("Authorization", ADMIN))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.signatures.length()").value(7));
  }

  private org.springframework.test.web.servlet.ResultActions importDefaults() throws Exception {
    String starter;
    try (var input =
        new org.springframework.core.io.ClassPathResource("signatures/defaults.json")
            .getInputStream()) {
      starter = new String(input.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
    }
    return mvc.perform(
            put("/api/v1/signature-feed")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(Map.of("document", starter))))
        .andExpect(status().isOk());
  }

  @Test
  void pastedJsonAndYamlAppendRulesWithoutReplacingDefaults() throws Exception {
    importDefaults().andExpect(jsonPath("$.signatures.length()").value(7));
    String yaml =
        """
        id: CUSTOM-YAML
        name: Custom pasted rule
        source: https://example.org/security
        category: LLM01:2025
        action: monitor
        target: prompt
        match:
          type: literal
          value: reveal internal credentials
        enabled: true
        """;
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", ADMIN)
                .contentType(MediaType.TEXT_PLAIN)
                .content(yaml))
        .andExpect(status().isCreated())
        .andExpect(header().string("Location", "/api/v1/signatures/CUSTOM-YAML"));
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", ADMIN)
                .contentType(MediaType.TEXT_PLAIN)
                .content(mapper.writeValueAsString(rule("CUSTOM-JSON"))))
        .andExpect(status().isCreated());
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", ADMIN)
                .contentType(MediaType.TEXT_PLAIN)
                .content(yaml))
        .andExpect(status().isConflict());
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", ADMIN)
                .contentType(MediaType.TEXT_PLAIN)
                .content("{bad json"))
        .andExpect(status().isBadRequest());
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", ADMIN)
                .contentType(MediaType.TEXT_PLAIN)
                .content("id: INCOMPLETE"))
        .andExpect(status().isBadRequest());
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", "Bearer test-gateway")
                .contentType(MediaType.TEXT_PLAIN)
                .content(yaml))
        .andExpect(status().isForbidden());
    mvc.perform(get("/api/v1/signature-feed").header("Authorization", ADMIN))
        .andExpect(jsonPath("$.signatures.length()").value(9));
  }

  @Test
  void defaultMigrationSeedsSevenOnceAndPreservesLaterChanges() throws Exception {
    var migrations = seedTestMigrations(null);
    migrations.clean();
    try {
      migrations.migrate();
      org.assertj.core.api.Assertions.assertThat(
              jdbc.queryForObject(
                  "SELECT COUNT(*) FROM signature_defaults_test.signature", Long.class))
          .isEqualTo(7);
      jdbc.update(
          "DELETE FROM signature_defaults_test.signature WHERE id = 'STARTER-INJECTION-PL-001'");
      jdbc.update(
          "UPDATE signature_defaults_test.signature SET document = ? WHERE id ="
              + " 'STARTER-INJECTION-EN-001'",
          mapper.writeValueAsString(rule("STARTER-INJECTION-EN-001")));
      jdbc.update(
          "INSERT INTO signature_defaults_test.signature(id, document, imported_at) VALUES(?, ?,"
              + " NOW())",
          "CUSTOM",
          mapper.writeValueAsString(rule("CUSTOM")));
      migrations.migrate();
      org.assertj.core.api.Assertions.assertThat(
              jdbc.queryForObject(
                  "SELECT COUNT(*) FROM signature_defaults_test.signature", Long.class))
          .isEqualTo(7);
      org.assertj.core.api.Assertions.assertThat(
              jdbc.queryForObject(
                  "SELECT COUNT(*) FROM signature_defaults_test.signature WHERE id ="
                      + " 'STARTER-INJECTION-PL-001'",
                  Long.class))
          .isZero();
      String custom =
          jdbc.queryForObject(
              "SELECT document FROM signature_defaults_test.signature WHERE id ="
                  + " 'STARTER-INJECTION-EN-001'",
              String.class);
      org.assertj.core.api.Assertions.assertThat(mapper.readTree(custom).path("action").asText())
          .isEqualTo("block");
    } finally {
      migrations.clean();
    }
  }

  @Test
  void upgradingExistingFeedPreservesCustomRulesAndConflictingIds() throws Exception {
    var migrations = seedTestMigrations(null);
    migrations.clean();
    try {
      seedTestMigrations("1").migrate();
      for (String id : java.util.List.of("CUSTOM", "STARTER-INJECTION-EN-001")) {
        jdbc.update(
            "INSERT INTO signature_defaults_test.signature(id, document, imported_at) VALUES(?, ?,"
                + " NOW())",
            id,
            mapper.writeValueAsString(rule(id)));
      }
      migrations.migrate();
      org.assertj.core.api.Assertions.assertThat(
              jdbc.queryForObject(
                  "SELECT COUNT(*) FROM signature_defaults_test.signature", Long.class))
          .isEqualTo(8);
      String retained =
          jdbc.queryForObject(
              "SELECT document FROM signature_defaults_test.signature WHERE id ="
                  + " 'STARTER-INJECTION-EN-001'",
              String.class);
      org.assertj.core.api.Assertions.assertThat(mapper.readTree(retained).path("action").asText())
          .isEqualTo("block");
    } finally {
      migrations.clean();
    }
  }

  private Flyway seedTestMigrations(String target) {
    var configuration =
        Flyway.configure()
            .dataSource(dataSource)
            .schemas("signature_defaults_test")
            .defaultSchema("signature_defaults_test")
            .cleanDisabled(false);
    if (target != null) configuration.target(target);
    return configuration.load();
  }

  @Test
  void additionsRespectFeedSizeLimit() throws Exception {
    jdbc.update(
        "INSERT INTO signature(id, document, imported_at) SELECT 'RULE-' || n, '{}', NOW() FROM"
            + " generate_series(1, 1000) n");
    mvc.perform(
            post("/api/v1/signatures")
                .header("Authorization", ADMIN)
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(rule("OVER-LIMIT"))))
        .andExpect(status().isConflict());
    org.assertj.core.api.Assertions.assertThat(
            jdbc.queryForObject("SELECT COUNT(*) FROM signature", Long.class))
        .isEqualTo(1000);
  }

  private Map<String, Object> rule(String id) {
    return Map.of(
        "id",
        id,
        "name",
        "Reveal instructions",
        "source",
        "https://example.org/reference",
        "category",
        "LLM01:2025",
        "action",
        "block",
        "target",
        "prompt",
        "match",
        Map.of("type", "literal", "value", "reveal system instructions"),
        "enabled",
        true);
  }
}
