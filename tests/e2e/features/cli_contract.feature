@e2e
Feature: jeeves CLI contract
  The built zipapp must honour its documented exit codes and stream discipline.
  These scenarios need no Jenkins at all, so they run anywhere the binary does
  and form the fast half of the suite.

  Background:
    Given no Jenkins connection is configured

  Scenario: Version matches the VERSION file
    When I run `jeeves --version`
    Then the exit code is 0
    And stdout reports the version from the VERSION file
    And stderr is empty

  Scenario: Help lists the headline options
    When I run `jeeves --help`
    Then the exit code is 0
    And stdout contains "--url"
    And stdout contains "--profile"
    And stdout contains "--format"
    And stdout contains "--no-colour"
    And stdout contains "--no-update-check"

  Scenario: Help lists the noun groups
    When I run `jeeves --help`
    Then the exit code is 0
    And stdout contains "build"
    And stdout contains "job"
    And stdout contains "node"
    And stdout contains "queue"
    And stdout contains "status"
    And stdout contains "whoami"

  Scenario: An unknown command is a usage error
    When I run `jeeves nonsense-command --no-colour`
    Then the exit code is 2
    And stderr contains "No such command"
    And stdout is empty

  Scenario: An invalid output format is a usage error
    When I run `jeeves --format bogus --no-colour status`
    Then the exit code is 2
    And stderr contains "Invalid value for '--format'"
    And stdout is empty

  Scenario: An invalid theme is a usage error
    When I run `jeeves --theme bogus --no-colour status`
    Then the exit code is 2
    And stderr contains "Invalid value for '--theme'"
    And stdout is empty

  # zsh rather than bash, deliberately. Click gates bash completion on the
  # *host's* bash version and warns on stderr below 4.4; macOS still ships
  # 3.2, so asserting a clean stderr for bash would pass on CI and fail on
  # every Mac. The warning itself is correct — a diagnostic, on stderr — so
  # the portable claim is the one that matters: the script reaches stdout,
  # because `eval "$(jeeves completions zsh)"` is how it gets used.
  Scenario: Completions are emitted on stdout alone
    When I run `jeeves completions zsh`
    Then the exit code is 0
    And stdout contains "_jeeves_completion"
    And stderr is empty

  Scenario: Bash completions still reach stdout on an old host bash
    When I run `jeeves completions bash`
    Then the exit code is 0
    And stdout contains "_jeeves_completion"
    And stdout does not contain "not supported"

  Scenario: An unknown shell is rejected
    When I run `jeeves completions bogusshell`
    Then the exit code is 2
    And stderr contains "Invalid value"
    And stdout is empty

  Scenario: Writing a default config honours the sandboxed XDG dirs
    When I run `jeeves --init-config`
    Then the exit code is 0
    And the config file exists in the sandbox
    And nothing was written directly to the home directory

  Scenario: Showing resolved config reports that none was found
    When I run `jeeves --show-config --no-colour`
    Then the exit code is 0
    And stdout contains "(none found)"
    And stderr is empty

  Scenario: A config file is picked up from the sandboxed XDG dir
    Given the config file contains "jenkins-url = 'http://config-was-read:8080'"
    When I run `jeeves --show-config --no-colour`
    Then the exit code is 0
    And stdout contains "http://config-was-read:8080"

  # The project's hard rule is "stdout for data, stderr for errors". The
  # mocked suite can check that too, but only for output that goes through
  # Click; this sees the real file descriptors, so it also catches anything
  # written around Click — a warning, the shiv preamble, a chatty dependency.
  # Such a stray line on stdout would corrupt `--format json` for a caller
  # piping us, and no in-process test would notice.
  Scenario Outline: An unreachable estate is reported on stderr, never stdout
    Given the Jenkins URL points at a closed port
    When I run `jeeves --no-colour <command>`
    Then the exit code is 1
    And stderr contains "quite unreachable"
    And stdout is empty

    Examples:
      | command   |
      | status    |
      | whoami    |
      | job list  |
      | node list |
      | queue     |

  Scenario: A connection failure stays an error even when JSON was asked for
    Given the Jenkins URL points at a closed port
    When I run `jeeves --format json --no-colour job list`
    Then the exit code is 1
    And stdout is empty
    And stderr contains "quite unreachable"
