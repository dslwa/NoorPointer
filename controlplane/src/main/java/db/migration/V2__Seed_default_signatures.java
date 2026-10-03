package db.migration;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.flywaydb.core.api.migration.BaseJavaMigration;
import org.flywaydb.core.api.migration.Context;

/** Installs the bundled defaults once, preserving existing rule IDs and later user changes. */
public class V2__Seed_default_signatures extends BaseJavaMigration {
  @Override
  public void migrate(Context context) throws Exception {
    var mapper = new ObjectMapper();
    try (var input = getClass().getResourceAsStream("/signatures/defaults.json")) {
      if (input == null) throw new IllegalStateException("Default signatures are missing");
      var defaults = mapper.readTree(input).path("signatures");
      if (!defaults.isArray() || defaults.size() != 7) {
        throw new IllegalStateException("Expected seven default signatures");
      }
      var connection = context.getConnection();
      try (var lock = connection.createStatement()) {
        lock.execute("LOCK TABLE signature IN SHARE ROW EXCLUSIVE MODE");
      }
      try (var insert =
          connection.prepareStatement(
              """
              INSERT INTO signature(id, document, imported_at)
              SELECT ?, ?, CURRENT_TIMESTAMP WHERE (SELECT COUNT(*) FROM signature) < 1000
              ON CONFLICT (id) DO NOTHING
              """)) {
        for (var signature : defaults) {
          insert.setString(1, signature.path("id").asText());
          insert.setString(2, mapper.writeValueAsString(signature));
          insert.executeUpdate();
        }
      }
    }
  }
}
