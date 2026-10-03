package pl.noorpointer.controller;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import pl.noorpointer.dto.DashboardResponse;
import pl.noorpointer.service.DashboardService;

@RestController
@RequestMapping("/api/v1/dashboard")
public class DashboardController {
  private final DashboardService dashboard;

  public DashboardController(DashboardService dashboard) {
    this.dashboard = dashboard;
  }

  @GetMapping
  public DashboardResponse get() {
    return dashboard.get();
  }
}
