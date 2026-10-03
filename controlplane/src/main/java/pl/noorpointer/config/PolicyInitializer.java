package pl.noorpointer.config;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;
import pl.noorpointer.service.PolicyService;

@Component
public class PolicyInitializer implements ApplicationRunner {
  private final PolicyService policies;

  public PolicyInitializer(PolicyService policies) {
    this.policies = policies;
  }

  @Override
  public void run(ApplicationArguments args) {
    policies.initializeDefaults();
  }
}
