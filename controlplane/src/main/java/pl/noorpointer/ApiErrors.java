package pl.noorpointer;

import java.util.Map;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.server.ResponseStatusException;

@RestControllerAdvice
class ApiErrors {
    @ExceptionHandler(ResponseStatusException.class)
    org.springframework.http.ResponseEntity<?> status(ResponseStatusException e) {
        return org.springframework.http.ResponseEntity.status(e.getStatusCode())
            .body(Map.of("status", e.getStatusCode().value(), "message", e.getReason() == null ? "Request rejected" : e.getReason()));
    }

    @ExceptionHandler({IllegalArgumentException.class, HttpMessageNotReadableException.class, MethodArgumentNotValidException.class})
    org.springframework.http.ResponseEntity<?> badRequest(Exception e) {
        String message = e instanceof IllegalArgumentException ? e.getMessage() : "Invalid request body or fields";
        return org.springframework.http.ResponseEntity.badRequest().body(Map.of("status", 400, "message", message));
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    org.springframework.http.ResponseEntity<?> conflict(Exception e) {
        return org.springframework.http.ResponseEntity.status(HttpStatus.CONFLICT)
            .body(Map.of("status", 409, "message", "Concurrent update or duplicate identifier; refresh and retry"));
    }
}
