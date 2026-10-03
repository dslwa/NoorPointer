package pl.noorpointer.document;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
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
}
