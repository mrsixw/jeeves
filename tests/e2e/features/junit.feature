@e2e @docker
Feature: JUnit test results against the real plugin

  `jeeves plugin junit report` reads the junit plugin's testReport export. The
  unit suite in tests/test_junit.py carries the coverage — filters, matrix
  children, the three readings of a 404. What it cannot do is confirm the
  real plugin's export has the shape it assumes: a `tree` reaching through
  suites into cases, status names as the plugin spells them, and counts that
  agree with the XML that was published.

  The seed job e2e-test-reporter publishes two passing tests, one failing and
  one skipped, and is guarded by the fixture inventory scenario.

  Background:
    Given a Jenkins estate
    And the job "e2e-test-reporter" has a completed build

  Scenario: The report's totals go to stderr and its rows to stdout
    When I run `jeeves --no-colour plugin junit report e2e-test-reporter`
    Then the exit code is 0
    And stderr contains "2 passed, 1 failed, 1 skipped"
    And stdout contains "test_passes"
    And stdout contains "test_skipped"
    And stdout contains "FAILED"
    And stdout does not contain "2 passed"

  Scenario: --failed keeps only the failure, with the plugin's detail
    When I run `jeeves --no-colour --format json plugin junit report e2e-test-reporter --failed`
    Then the exit code is 0
    And stdout is valid JSON
    And the JSON payload has exactly 1 record
    And stdout contains "test_fails"
    And stdout contains "e2e-expected-failure"

  # A build that never ran the junit step has no testReport at all. The
  # fixture user is an administrator, so the plugin manager can be asked and
  # the answer is the precise one rather than "undetermined".
  Scenario: A build that published nothing says so and exits 1
    Given the job "e2e-pipeline" has a completed build
    When I run `jeeves --no-colour plugin junit report e2e-pipeline`
    Then the exit code is 1
    And stderr contains "published no test results"
    And stdout is empty
