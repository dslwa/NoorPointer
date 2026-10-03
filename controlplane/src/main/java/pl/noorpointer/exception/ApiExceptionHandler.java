package pl.noorpointer.exception;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.ConstraintViolationException;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.BindException;
import org.springframework.web.HttpMediaTypeNotSupportedException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MissingServletRequestParameterException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.method.annotation.HandlerMethodValidationException;
import org.springframework.web.method.annotation.MethodArgumentTypeMismatchException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.resource.NoResourceFoundException;
import pl.noorpointer.dto.ApiError;

@RestControllerAdvice
public class ApiExceptionHandler {
  private static final Logger LOG = LoggerFactory.getLogger(ApiExceptionHandler.class);

  @ExceptionHandler(ResponseStatusException.class)
  public ResponseEntity<ApiError> status(
      ResponseStatusException error, HttpServletRequest request) {
    return response(
        error.getStatusCode().value(),
        error.getReason() == null ? "Request rejected" : error.getReason(),
        request);
  }

  @ExceptionHandler({
    IllegalArgumentException.class,
    HttpMessageNotReadableException.class,
    BindException.class,
    HandlerMethodValidationException.class,
    MethodArgumentTypeMismatchException.class,
    MissingServletRequestParameterException.class,
    ConstraintViolationException.class
  })
  public ResponseEntity<ApiError> badRequest(Exception error, HttpServletRequest request) {
    String message = "Invalid request body or parameters";
    if (error instanceof BindException binding) {
      message =
          binding.getBindingResult().getFieldErrors().stream()
              .map(field -> field.getField() + ": " + field.getDefaultMessage())
              .distinct()
              .limit(8)
              .collect(java.util.stream.Collectors.joining("; "));
      if (message.isBlank()) message = "Invalid request fields";
    } else if (error instanceof IllegalArgumentException) {
      message = error.getMessage() == null ? message : error.getMessage();
    }
    return response(400, message, request);
  }

  @ExceptionHandler(DataIntegrityViolationException.class)
  public ResponseEntity<ApiError> conflict(Exception error, HttpServletRequest request) {
    return response(409, "Concurrent update or duplicate identifier; refresh and retry", request);
  }

  @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
  public ResponseEntity<ApiError> methodNotAllowed(
      HttpRequestMethodNotSupportedException error, HttpServletRequest request) {
    var result = response(405, "HTTP method is not supported for this resource", request);
    var headers = new org.springframework.http.HttpHeaders();
    if (error.getSupportedHttpMethods() != null) headers.setAllow(error.getSupportedHttpMethods());
    return new ResponseEntity<>(result.getBody(), headers, HttpStatus.METHOD_NOT_ALLOWED);
  }

  @ExceptionHandler(HttpMediaTypeNotSupportedException.class)
  public ResponseEntity<ApiError> unsupportedMediaType(
      Exception error, HttpServletRequest request) {
    return response(415, "Unsupported content type", request);
  }

  @ExceptionHandler(NoResourceFoundException.class)
  public ResponseEntity<ApiError> notFound(Exception error, HttpServletRequest request) {
    return response(404, "Resource not found", request);
  }

  @ExceptionHandler(Exception.class)
  public ResponseEntity<ApiError> unexpected(Exception error, HttpServletRequest request) {
    LOG.error("Unhandled request failure", error);
    return response(500, "Internal server error", request);
  }

  private ResponseEntity<ApiError> response(
      int status, String message, HttpServletRequest request) {
    return ResponseEntity.status(status)
        .body(new ApiError(status, message, request.getRequestURI(), Instant.now()));
  }
}
