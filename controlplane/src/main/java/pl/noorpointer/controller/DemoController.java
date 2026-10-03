package pl.noorpointer.controller;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import pl.noorpointer.dto.DemoBatchResponse;
import pl.noorpointer.service.DemoService;

@RestController
@RequestMapping("/api/v1/demo-batches")
public class DemoController {
  private final DemoService demo;

  public DemoController(DemoService demo) {
    this.demo = demo;
  }

  @PostMapping
  @ResponseStatus(HttpStatus.CREATED)
  public DemoBatchResponse create() {
    return demo.createBatch();
  }
}
