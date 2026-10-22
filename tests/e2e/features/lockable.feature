@e2e @docker
Feature: Lockable resources against the real plugin

  `jeeves plugin lockable-resources` talks to a third-party plugin rather than
  to base Jenkins, which makes it the part of jeeves with the least to gain
  from mocks. The unit suite in tests/test_lockable.py carries the coverage —
  every status code, every reason, the 404 disambiguation table. What it cannot
  do is confirm that the real plugin behaves the way those tests assume.

  So the scenarios here validate the assumptions: that `reserve` really
  reserves, that labels arrive as a space-separated string needing a split,
  that createResource and deleteResource exist at all in a current release,
  and that a resource held by a running build looks different from one merely
  reserved.

  The resources are declared in casc.yaml — e2e-lock-free, e2e-lock-spare and
  e2e-lock-held — and the first scenario guards those names.

  Background:
    Given a Jenkins estate

  Scenario: The lockable fixture is furnished as documented
    Then the lockable fixture inventory is as documented

  # ── reading the roster ────────────────────────────────────────────────────

  # The butler's header is an info line and belongs on stderr; the table of
  # resources is data and belongs on stdout. Proving the split over the real
  # file descriptors is the whole reason this layer exists.
  Scenario: The roster lists the declared resources on the right streams
    When I run `jeeves --no-colour plugin lockable-resources list`
    Then the exit code is 0
    And stderr contains "under lock and key"
    And stdout contains "e2e-lock-free"
    And stdout contains "e2e-lock-spare"
    And stdout does not contain "under lock and key"

  Scenario: The roster as JSON carries the documented keys
    When I run `jeeves --no-colour --format json plugin lockable-resources list`
    Then the exit code is 0
    And stdout is valid JSON
    And every record in the JSON payload has a "name" key
    And every record in the JSON payload has a "state" key
    And every record in the JSON payload has a "labels" key

  # The plugin sends labels as one space-separated string. jeeves splits it,
  # and only the real plugin can confirm the format being split is the real
  # one. Two resources share e2e-pool and one also has linux, so requiring
  # both labels tells an AND apart from an OR — with a single labelled
  # resource the bug would pass.
  Scenario: A label filter requires every label given, not any of them
    When I run `jeeves --no-colour plugin lockable-resources list --label e2e-pool`
    Then the exit code is 0
    And stdout contains "e2e-lock-free"
    And stdout contains "e2e-lock-spare"
    When I run `jeeves --no-colour plugin lockable-resources list --label e2e-pool --label linux`
    Then the exit code is 0
    And stdout contains "e2e-lock-free"
    And stdout does not contain "e2e-lock-spare"

  Scenario: Show reports a single resource and its description
    When I run `jeeves --no-colour plugin lockable-resources show e2e-lock-free`
    Then the exit code is 0
    And stdout contains "e2e-lock-free"
    And stdout contains "Reserve and release me."

  # The plugin has no per-resource endpoint, so `show` filters the roster. An
  # unknown name must therefore be an error and not an empty table.
  Scenario: Show on an unknown resource is an error, not an empty table
    When I run `jeeves --no-colour plugin lockable-resources show no-such-resource`
    Then the exit code is 1
    And stdout is empty
    And stderr contains "no resource by the name"

  # ── reserving ─────────────────────────────────────────────────────────────

  # One scenario, because each step depends on the previous having run and a
  # scenario is the only place Gherkin lets that be stated. It also covers the
  # idempotence contract: asking again for a state you already hold says so
  # and exits 0 rather than failing.
  Scenario: A resource is reserved, reported, re-reserved idempotently, and released
    When I run `jeeves --no-colour plugin lockable-resources reserve e2e-lock-free --reason "end-to-end"`
    Then the exit code is 0
    And Jenkins reports the resource "e2e-lock-free" as reserved by "jeeves-e2e"
    When I run `jeeves --no-colour plugin lockable-resources show e2e-lock-free`
    Then the exit code is 0
    And stdout contains "reserved"
    And stdout contains "jeeves-e2e"
    # Already ours: the plugin answers 423, and jeeves has to recognise that
    # the holder is the caller rather than report a conflict.
    When I run `jeeves --no-colour plugin lockable-resources reserve e2e-lock-free`
    Then the exit code is 0
    And stdout contains "already reserved"
    When I run `jeeves --no-colour plugin lockable-resources unreserve e2e-lock-free`
    Then the exit code is 0
    And Jenkins reports the resource "e2e-lock-free" as free
    # Already free: idempotent in the other direction.
    When I run `jeeves --no-colour plugin lockable-resources unreserve e2e-lock-free`
    Then the exit code is 0
    And stdout contains "already at liberty"

  Scenario: Reset on an idle resource reports it was already in order
    When I run `jeeves --no-colour plugin lockable-resources reset e2e-lock-spare`
    Then the exit code is 0
    And Jenkins reports the resource "e2e-lock-spare" as free

  # ── locked by a build, which is not the same as reserved ──────────────────

  # `locked` is unreachable by reserving: it takes a build inside the plugin's
  # lock step, and only then do lockCause and buildName carry anything. Those
  # fields are exactly the part of the record shape a mock can invent freely.
  Scenario: A resource held by a running build reads as locked, not reserved
    Given a build is holding the resource "e2e-lock-held"
    When I run `jeeves --no-colour --format json plugin lockable-resources list --state locked`
    Then the exit code is 0
    And stdout is valid JSON
    And stdout contains "e2e-lock-held"
    When I run `jeeves --no-colour plugin lockable-resources show e2e-lock-held`
    Then the exit code is 0
    And stdout contains "locked"
    # The holding build's name, which only a real lock populates. Verified
    # against the fixture: while held, the plugin reports locked=true,
    # reserved=false, reservedBy=null, and buildName set — so a locked
    # resource has no holder, and `state` must prefer locked over reserved.
    And stdout contains "e2e-lock-holder"

  # ── the register itself ───────────────────────────────────────────────────

  # createResource and deleteResource are @Restricted(NoExternalUse) in the
  # plugin, so they are UI-facing rather than contract, and absent from older
  # releases. This proves they exist and work in the pinned version — the only
  # way to know jeeves' "plugin too old" branch is not the normal case.
  Scenario: A resource is added to the register and struck off again
    When I run `jeeves --no-colour plugin lockable-resources add e2e-lock-temp --description "added by the suite" --label e2e-temp`
    Then the exit code is 0
    And Jenkins has a resource named "e2e-lock-temp"
    When I run `jeeves --no-colour plugin lockable-resources list --label e2e-temp`
    Then the exit code is 0
    And stdout contains "e2e-lock-temp"
    # Adding it again is the 409 path, which is idempotent by contract.
    When I run `jeeves --no-colour plugin lockable-resources add e2e-lock-temp`
    Then the exit code is 0
    And stdout contains "already in the register"
    When I run `jeeves --no-colour plugin lockable-resources remove e2e-lock-temp --yes`
    Then the exit code is 0
    And Jenkins has no resource named "e2e-lock-temp"
    # Removing what is not there is idempotent too, and must not be mistaken
    # for the plugin being absent — both answer 404.
    When I run `jeeves --no-colour plugin lockable-resources remove e2e-lock-temp --yes`
    Then the exit code is 0
    And stdout contains "never on the register"

  # Piped rather than attached to a terminal, which is how CI runs it, so the
  # confirmation prompt must not fire and must not hang waiting for input.
  Scenario: Remove does not prompt when stdin is not a terminal
    When I run `jeeves --no-colour plugin lockable-resources add e2e-lock-noprompt`
    Then the exit code is 0
    When I run `jeeves --no-colour plugin lockable-resources remove e2e-lock-noprompt`
    Then the exit code is 0
    And Jenkins has no resource named "e2e-lock-noprompt"
