package pl.noorpointer.controller.compatibility;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import pl.noorpointer.dto.AuditFilter;
import pl.noorpointer.dto.AuditReceipt;
import pl.noorpointer.service.AuditExportService;
import pl.noorpointer.service.LegacyAuditService;
import pl.noorpointer.web.ExportResponses;

@RestController
@RequestMapping("/api/v1/audit")
public class LegacyAuditController {
  private final LegacyAuditService audit;
  private final AuditExportService exports;

  public LegacyAuditController(LegacyAuditService audit, AuditExportService exports) {
    this.audit = audit;
    this.exports = exports;
  }

  @PostMapping("/events")
  public AuditReceipt ingest(@RequestBody JsonNode event) {
    return audit.ingest(event);
  }

  @GetMapping("/export")
  public ResponseEntity<String> export(
      @RequestParam(defaultValue = "json") String format, @ModelAttribute AuditFilter filter) {
    return ExportResponses.of(exports.export(format, filter));
  }
}
