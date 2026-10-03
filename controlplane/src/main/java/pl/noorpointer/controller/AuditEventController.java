package pl.noorpointer.controller;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.util.UriComponentsBuilder;
import pl.noorpointer.dto.AuditFilter;
import pl.noorpointer.dto.AuditReceipt;
import pl.noorpointer.dto.PageResponse;
import pl.noorpointer.service.AuditExportService;
import pl.noorpointer.service.AuditService;
import pl.noorpointer.web.ExportResponses;

@RestController
@RequestMapping("/api/v1/audit-events")
public class AuditEventController {
  private final AuditService audit;
  private final AuditExportService exports;

  public AuditEventController(AuditService audit, AuditExportService exports) {
    this.audit = audit;
    this.exports = exports;
  }

  @GetMapping
  public PageResponse<JsonNode> list(
      @ModelAttribute AuditFilter filter,
      @RequestParam(defaultValue = "0") @Min(0) @Max(100000) int page,
      @RequestParam(defaultValue = "20") @Min(1) @Max(100) int size) {
    return audit.list(filter, page, size);
  }

  @GetMapping("/{id}")
  public JsonNode get(@PathVariable String id) {
    return audit.get(id);
  }

  @GetMapping("/export")
  public ResponseEntity<String> export(
      @RequestParam(defaultValue = "json") String format, @ModelAttribute AuditFilter filter) {
    return ExportResponses.of(exports.export(format, filter));
  }

  @PostMapping
  public ResponseEntity<AuditReceipt> create(@RequestBody JsonNode event) {
    var receipt = audit.ingest(event);
    if (!receipt.accepted()) return ResponseEntity.ok(receipt);
    var location =
        UriComponentsBuilder.fromPath("/api/v1/audit-events/{id}")
            .encode()
            .buildAndExpand(receipt.id())
            .toUri();
    return ResponseEntity.created(location).body(receipt);
  }
}
