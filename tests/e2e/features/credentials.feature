@e2e @docker
Feature: Credential metadata against the real plugin

  `jeeves plugin credentials` reads the credentials plugin's exports, and only
  their metadata. The unit suite in tests/test_credentials.py carries the
  coverage — the folder walk, the filters, every error. What it cannot do is
  confirm the real plugin exports the shape it assumes: stores and domains as
  maps, a `tree` query reaching through both, and a folder exporting only its
  own store, never its parent's.

  Above all, these scenarios prove the one property this command must keep:
  the fixture's secret values, fixed and inert, never appear in its output.

  e2e-secret-text and e2e-domain-login are declared in casc.yaml;
  e2e-folder-secret is created in e2e-folder's own store by the fixture.

  Background:
    Given a Jenkins estate

  Scenario: The credentials fixture is furnished as documented
    Then the credentials fixture inventory is as documented

  Scenario: The root credentials are listed on the right streams
    When I run `jeeves --no-colour plugin credentials list`
    Then the exit code is 0
    And stderr contains "keys to the house"
    And stdout contains "e2e-secret-text"
    And stdout contains "Secret text"
    And stdout contains "e2e-domain-login"
    And stdout does not contain "e2e-folder-secret"
    And stdout does not contain "keys to the house"

  Scenario: No secret value ever reaches the output
    When I run `jeeves --no-colour --format json plugin credentials list --folder e2e-folder`
    Then the exit code is 0
    And stdout is valid JSON
    And every record in the JSON payload has a "type" key
    And stdout does not contain "e2e-not-really-a-secret"
    And stdout does not contain "e2e-not-really-a-password"
    And stdout does not contain "e2e-not-really-a-folder-secret"

  # Jenkins exports only a folder's own store, so the root's credentials can
  # appear here only because jeeves walked up to fetch them.
  Scenario: A folder sees its own credentials and those it inherits
    When I run `jeeves --no-colour plugin credentials list --folder e2e-folder`
    Then the exit code is 0
    And stdout contains "e2e-folder-secret"
    And stdout contains "e2e-secret-text"

  Scenario: A domain filter tells a named domain from the global one
    When I run `jeeves --no-colour plugin credentials list --domain e2e-domain`
    Then the exit code is 0
    And stdout contains "e2e-domain-login"
    And stdout does not contain "e2e-secret-text"

  Scenario: An unknown credential is an error on stderr
    When I run `jeeves --no-colour plugin credentials show no-such-credential`
    Then the exit code is 1
    And stderr contains "I find no credential by the id 'no-such-credential'"
    And stdout is empty

  Scenario: An unknown folder is an error, not an empty list
    When I run `jeeves --no-colour plugin credentials list --folder no-such-folder`
    Then the exit code is 1
    And stderr contains "I find no folder 'no-such-folder'"
    And stdout is empty
