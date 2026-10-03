package pl.noorpointer.web;

import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import pl.noorpointer.dto.AuditExport;

public final class ExportResponses {
  private ExportResponses() {}

  public static ResponseEntity<String> of(AuditExport export) {
    return ResponseEntity.ok()
        .contentType(MediaType.parseMediaType(export.contentType()))
        .header(
            HttpHeaders.CONTENT_DISPOSITION,
            ContentDisposition.attachment().filename(export.filename()).build().toString())
        .body(export.body());
  }
}
