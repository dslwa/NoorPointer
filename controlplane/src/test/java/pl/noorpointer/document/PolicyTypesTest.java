package pl.noorpointer.document;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

class PolicyTypesTest {
  private final DocumentService documents;

  PolicyTypesTest() throws Exception {
    documents = new DocumentService(new ObjectMapper());
  }

  @ParameterizedTest
  @ValueSource(
      strings = {
        "email",
        "pesel",
        "iban",
        "card",
        "phone",
        "first_name",
        "last_name",
        "full_name",
        "date_of_birth",
        "postal_code"
      })
  void acceptsExistingAndNewPersonalDataTypes(String type) {
    var policy = documents.profile("balanced");
    var types =
        (com.fasterxml.jackson.databind.node.ArrayNode)
            policy.path("controls").path("pii_regex").path("types");
    types.removeAll().add(type);
    documents.validate("policy", policy);
  }

  @Test
  void stillRejectsUnknownPersonalDataTypes() {
    var policy = documents.profile("balanced");
    var types =
        (com.fasterxml.jackson.databind.node.ArrayNode)
            policy.path("controls").path("pii_regex").path("types");
    types.add("unsupported_type");
    assertThatThrownBy(() -> documents.validate("policy", policy))
        .isInstanceOf(IllegalArgumentException.class);
  }

  @ParameterizedTest
  @ValueSource(strings = {"permissive", "balanced", "strict", "permissive-output", "balanced-output", "strict-output"})
  void profilesSatisfyTheSchema(String name) {
    var profile = documents.profile(name);
    documents.validate("policy", profile);
    assertThat(profile.path("controls").has("pii_ner")).isEqualTo(name.endsWith("-output"));
    assertThat(profile.path("controls").has("leakage")).isEqualTo(name.endsWith("-output"));
  }

  @ParameterizedTest
  @ValueSource(strings = {"prompt_injection", "content_safety", "attack_signatures", "agent_loops", "mcp_tools", "leakage"})
  void verdictOnlyControlsCannotRedact(String control) {
    var profile = documents.profile("balanced-output");
    ((ObjectNode) profile.path("controls").path(control)).put("action", "redact");
    assertThatThrownBy(() -> documents.validate("policy", profile)).isInstanceOf(IllegalArgumentException.class);
  }

  @Test
  void leakageIsOutputOnlyAndConfigurationIsBounded() {
    for (var invalid : new String[] {"{\"directions\":[\"input\"]}", "{\"threshold\":1.01}",
        "{\"ngram\":1}", "{\"ngram\":21}", "{\"timeout_ms\":30001}", "{\"canaries\":[\"\"]}"}) {
      var profile = documents.profile("balanced-output");
      ((ObjectNode) profile.path("controls").path("leakage")).setAll((ObjectNode) documents.read(invalid));
      assertThatThrownBy(() -> documents.validate("policy", profile)).isInstanceOf(IllegalArgumentException.class);
    }
  }

  @Test
  void piiRequiresValidEntitiesAndNonemptyUniqueDirections() {
    for (var invalid : new String[] {"{\"entities\":[]}", "{\"entities\":[\"email\"]}",
        "{\"entities\":[\"PERSON\",\"PERSON\"]}", "{\"directions\":[]}",
        "{\"directions\":[\"output\",\"output\"]}", "{\"threshold\":-0.1}"}) {
      var profile = documents.profile("balanced-output");
      ((ObjectNode) profile.path("controls").path("pii_ner")).setAll((ObjectNode) documents.read(invalid));
      assertThatThrownBy(() -> documents.validate("policy", profile)).isInstanceOf(IllegalArgumentException.class);
    }
  }
}
