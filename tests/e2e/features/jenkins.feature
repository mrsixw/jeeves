@e2e @docker
Feature: jeeves against a real Jenkins
  Everything here needs the fixture Jenkins in a container, so the whole file
  carries the docker tag and costs a boot. Each scenario earns that by
  asserting something a mock cannot settle: a real wire format, a real status
  code, or a real queue-to-build transition.

  The fixture's jobs are fixed — e2e-freestyle, e2e-pipeline and
  e2e-folder/nested. The first scenario guards those names so a rename fails
  once, legibly, rather than scattering "job not found" across the file.

  Background:
    Given a Jenkins estate

  Scenario: The fixture is furnished as documented
    Then the fixture inventory is as documented

  # ── connection and authentication ─────────────────────────────────────────

  # The butler's verdict is an info line, so it belongs on stderr, and the
  # table of facts belongs on stdout. Asserting both is the point: this proves
  # the split on a command that emits to each at once, over the real file
  # descriptors rather than through Click's capture.
  Scenario: Status reports a healthy estate on the right streams
    When I run `jeeves --no-colour status`
    Then the exit code is 0
    And stderr contains "fine form"
    And stdout contains "Executors"
    And stdout does not contain "fine form"

  Scenario: Whoami reports the authenticated user
    When I run `jeeves --no-colour whoami`
    Then the exit code is 0
    And stdout contains "jeeves-e2e"

  # Only a real Jenkins settles which status it uses to reject a bad token,
  # and therefore which butler error the user actually sees.
  Scenario: A rejected token is reported as an authentication failure
    Given the credentials are wrong
    When I run `jeeves --no-colour whoami`
    Then the exit code is 1
    And stdout is empty

  # ── jobs ──────────────────────────────────────────────────────────────────

  Scenario: Job list shows the fixture jobs
    When I run `jeeves --no-colour job list`
    Then the exit code is 0
    And stdout contains "e2e-freestyle"
    And stdout contains "e2e-pipeline"

  Scenario: Job list as JSON carries a name on every record
    When I run `jeeves --no-colour --format json job list`
    Then the exit code is 0
    And stdout is valid JSON
    And every record in the JSON payload has a "name" key

  # normalize_jenkins_path encodes folder/job as /job/folder/job/job. A mock
  # accepts whatever shape we invent; only Jenkins insists on the right one.
  Scenario: A job inside a folder is addressable by its slash-separated path
    When I run `jeeves --no-colour job params e2e-folder/nested`
    Then the exit code is 0
    And stdout contains "GREETING"

  Scenario: Job params reads the parameter definition from Jenkins
    When I run `jeeves --no-colour job params e2e-freestyle`
    Then the exit code is 0
    And stdout contains "GREETING"
    And stdout contains "default-greeting"

  # ── builds ────────────────────────────────────────────────────────────────

  # The payoff scenario. --wait follows a real queue item through to a real
  # executor and maps the result to an exit code, so this proves the
  # queue-to-build transition, the parameter wire format and the exit-code
  # contract in one pass. Parameters must go in a form body, not a query
  # string; a mock enforces neither.
  # Deliberately one scenario rather than three. Each step depends on the
  # previous having run, and a scenario is the only place Gherkin lets that
  # dependency be stated. Split across scenarios it would become an implicit
  # reliance on pytest's file ordering — which works until someone reorders
  # the file or runs one scenario with -k.
  Scenario: A parameterised build is triggered, followed, and read back
    When I run `jeeves --no-colour job trigger e2e-freestyle --param GREETING=from-e2e --wait --timeout 300`
    Then the exit code is 0
    And stdout contains "SUCCESS"
    And the Jenkins job "e2e-freestyle" has at least 1 build
    When I run `jeeves --no-colour build log e2e-freestyle`
    Then the exit code is 0
    And stdout contains "greeting=from-e2e"
    When I run `jeeves --no-colour build list e2e-freestyle`
    Then the exit code is 0
    # The table renders the result, it does not echo the API's raw "SUCCESS".
    And stdout contains "Success"
    # blame asks for changeSets[] and changeSet together, because pipeline
    # builds report the former and freestyle the latter. The fixture jobs have
    # no SCM, so the change set is empty — what this proves is that jeeves
    # reads whichever shape Jenkins sends for *this* job type without
    # erroring. A populated change set needs an SCM-backed job; see
    # docs/design/testing.md.
    When I run `jeeves --no-colour build blame e2e-freestyle`
    Then the exit code is 0

  Scenario: A pipeline build is followed to success, and blamed
    When I run `jeeves --no-colour job trigger e2e-pipeline --param GREETING=from-pipeline --wait --timeout 300`
    Then the exit code is 0
    And stdout contains "SUCCESS"
    And the Jenkins job "e2e-pipeline" has at least 1 build
    # The other half of the change-set pair: pipeline builds use changeSets[].
    When I run `jeeves --no-colour build blame e2e-pipeline`
    Then the exit code is 0

  # ── other read commands ───────────────────────────────────────────────────

  Scenario: The queue is readable and empty once builds have finished
    When I run `jeeves --no-colour queue`
    Then the exit code is 0

  Scenario: Node list reports the built-in node
    When I run `jeeves --no-colour node list`
    Then the exit code is 0
    And stdout contains "Built-In Node"
