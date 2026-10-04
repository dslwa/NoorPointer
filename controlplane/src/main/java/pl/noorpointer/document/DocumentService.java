package pl.noorpointer.document;

import com.fasterxml.jackson.core.JsonParser;
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.dataformat.yaml.YAMLFactory;
import com.networknt.schema.JsonSchema;
import com.networknt.schema.JsonSchemaFactory;
import com.networknt.schema.SpecVersion;
import java.io.IOException;
import java.util.HashMap;
import java.util.Map;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Component;

@Component
public class DocumentService {
  private final ObjectMapper json;
  private final ObjectMapper yaml =
      new ObjectMapper(new YAMLFactory())
          .enable(JsonParser.Feature.STRICT_DUPLICATE_DETECTION)
          .enable(DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
  private final Map<String, JsonNode> contracts = new HashMap<>();
  private final Map<String, JsonSchema> validators = new HashMap<>();

  public DocumentService(ObjectMapper json) throws IOException {
    this.json = json;
    for (String name : new String[] {"policy", "audit", "signatures"}) {
      try (var input =
          new ClassPathResource("contracts/" + name + ".schema.json").getInputStream()) {
        var schema = json.readTree(input);
        contracts.put(name, schema);
        validators.put(
            name, JsonSchemaFactory.getInstance(SpecVersion.VersionFlag.V202012).getSchema(schema));
      }
    }
  }

  public JsonNode parse(String text) {
    if (text == null || text.isBlank() || text.length() > 1_000_000) {
      throw new IllegalArgumentException(
          "Document must contain between 1 and 1,000,000 characters");
    }
    try {
      JsonNode node = yaml.readTree(text);
      if (node == null || !node.isObject())
        throw new IllegalArgumentException("Expected a JSON or YAML object");
      return node;
    } catch (IOException e) {
      throw new IllegalArgumentException("Invalid JSON or YAML document");
    }
  }

  public void validate(String contract, JsonNode node) {
    var errors = validators.get(contract).validate(node);
    if (!errors.isEmpty()) {
      throw new IllegalArgumentException(
          errors.stream()
              .map(Object::toString)
              .sorted()
              .limit(8)
              .collect(java.util.stream.Collectors.joining("; ")));
    }
    if (contract.equals("policy")) {
      var subjects = new java.util.HashSet<String>();
      for (JsonNode budget : node.path("budgets")) {
        if (!subjects.add(budget.path("subject").asText()))
          throw new IllegalArgumentException("Duplicate budget subject");
      }
    }
  }

  public JsonNode schema(String name) {
    var schema = contracts.get(name);
    if (schema == null)
      throw new org.springframework.web.server.ResponseStatusException(
          org.springframework.http.HttpStatus.NOT_FOUND, "Unknown contract");
    return schema;
  }

  public JsonNode read(String stored) {
    try {
      return json.readTree(stored);
    } catch (IOException e) {
      throw new IllegalStateException("Cannot read stored document", e);
    }
  }

  public String write(Object value) {
    try {
      return json.writeValueAsString(value);
    } catch (IOException e) {
      throw new IllegalStateException("Cannot serialize document", e);
    }
  }

  public JsonNode profile(String name) {
    if (!java.util.Set.of("permissive", "balanced", "strict",
        "permissive-output", "balanced-output", "strict-output").contains(name)) {
      throw new org.springframework.web.server.ResponseStatusException(
          org.springframework.http.HttpStatus.NOT_FOUND, "Unknown profile");
    }
    try (var input = new ClassPathResource("profiles/" + name + ".json").getInputStream()) {
      return json.readTree(input);
    } catch (IOException e) {
      throw new IllegalStateException(e);
    }
  }
}
