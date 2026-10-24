@e2e @docker
Feature: Pipeline input steps against the real plugin

  `jeeves plugin input` settles builds paused at an `input` step, through the
  pipeline-input-step plugin rather than base Jenkins. The unit suite in
  tests/test_pipeline_input.py carries the coverage — every reason, the
  ambiguity rules, the defaults filling. What it cannot do is confirm the real
  plugin accepts what jeeves sends.

  So these scenarios validate the wire: that /input/ appears once a build
  pauses, that `proceed` parses the `json` form body jeeves builds (the
  console echoes the value Jenkins actually handed the pipeline), that `abort`
  really aborts, and that the confirming re-read sees the input settle.

  The seed job is e2e-input-waiter, guarded by the fixture inventory scenario.

  Background:
    Given a Jenkins estate

  Scenario: A paused input is listed on the right streams
    Given a build of "e2e-input-waiter" is paused at an input
    When I run `jeeves --no-colour plugin input list e2e-input-waiter`
    Then the exit code is 0
    And stderr contains "awaits your word"
    And stdout contains "Release"
    And stdout contains "Ship it?"
    And stdout contains "TARGET (string)"
    And stdout does not contain "awaits your word"
    When I run `jeeves --no-colour plugin input reject e2e-input-waiter`
    Then the exit code is 0

  # The parameter travels inside a JSON document inside a form field. Only
  # the real plugin can say whether that is the shape it parses, so the
  # assertion is on the pipeline's own echo of the value it received.
  Scenario: Approving with a parameter lets the build proceed with that value
    Given a build of "e2e-input-waiter" is paused at an input
    When I run `jeeves --no-colour plugin input approve e2e-input-waiter --param TARGET=us`
    Then the exit code is 0
    And stdout contains "may proceed"
    And the last build of "e2e-input-waiter" finishes with result "SUCCESS"
    And the console of the last build of "e2e-input-waiter" contains "target=us"

  # proceedEmpty would hand the pipeline null; jeeves sends the declared
  # default instead, and the console proves which one arrived.
  Scenario: Approving without parameters sends the declared defaults
    Given a build of "e2e-input-waiter" is paused at an input
    When I run `jeeves --no-colour plugin input approve e2e-input-waiter`
    Then the exit code is 0
    And the last build of "e2e-input-waiter" finishes with result "SUCCESS"
    And the console of the last build of "e2e-input-waiter" contains "target=eu"

  Scenario: Rejecting aborts the build
    Given a build of "e2e-input-waiter" is paused at an input
    When I run `jeeves --no-colour plugin input reject e2e-input-waiter`
    Then the exit code is 0
    And stdout contains "conveyed your regrets"
    And the last build of "e2e-input-waiter" finishes with result "ABORTED"
    And Jenkins reports nothing pending on the last build of "e2e-input-waiter"

  # Idempotent per #108: once settled, asking again is not an error.
  Scenario: Settling a build that awaits nothing exits 0
    Given a build of "e2e-input-waiter" is paused at an input
    When I run `jeeves --no-colour plugin input approve e2e-input-waiter`
    Then the exit code is 0
    And the last build of "e2e-input-waiter" finishes with result "SUCCESS"
    When I run `jeeves --no-colour plugin input approve e2e-input-waiter`
    Then the exit code is 0
    And stdout contains "Nothing wanted doing"

  # An unknown parameter is refused before any POST, so the build stays
  # paused — which Jenkins, not jeeves, confirms.
  Scenario: An unknown parameter is refused and the build stays paused
    Given a build of "e2e-input-waiter" is paused at an input
    When I run `jeeves --no-colour plugin input approve e2e-input-waiter --param NOPE=1`
    Then the exit code is 1
    And stderr contains "no parameter named 'NOPE'"
    And stdout is empty
    When I run `jeeves --no-colour plugin input reject e2e-input-waiter`
    Then the exit code is 0
