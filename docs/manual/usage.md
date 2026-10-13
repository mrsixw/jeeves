# Usage Guide

## Basic usage

```bash
jeeves
jeeves status
jeeves --theme rainbow
jeeves --no-colour
```

## Themes

```bash
jeeves --theme default
jeeves --theme dark
jeeves --theme light
jeeves --theme mono       # no colour
jeeves --theme rainbow    # cycling ROYGBIV
```

## Seasonal colours

Seasonal colours are on by default. They change automatically around holidays:

```bash
jeeves                                  # western calendar (default)
jeeves --seasonal-calendar jewish       # Hanukkah, Passover, etc.
jeeves --no-seasonal-colours            # disable entirely
```

## Working with jobs

```bash
jeeves job list                              # list jobs and their status
jeeves job list --folder platform            # limit to a folder
jeeves job params my-pipeline                # list the job's build parameters
jeeves job trigger my-pipeline --param ENV=prod
jeeves job trigger my-pipeline --wait        # follow it through to the verdict
jeeves job trigger my-pipeline --wait --timeout 600 --poll-interval 10
```

With `--wait`, jeeves follows the request through the queue and the running
build, and the exit code mirrors the verdict — `0` success, `1` failure,
`2` unstable, `3` aborted or cancelled, `124` timeout — so it composes in
scripts: `jeeves job trigger deploy --wait && ./smoke-test.sh`.

## Working with builds

```bash
jeeves build summary my-pipeline             # last / successful / failed builds
jeeves build list my-pipeline                # recent build history
jeeves build list my-pipeline --limit 50 --result FAILURE
jeeves build show my-pipeline 142            # a specific build
jeeves build log my-pipeline 142             # console output (default: lastBuild)
jeeves build log my-pipeline --follow        # stream a running build live (tail -f)
jeeves build cancel my-pipeline 142          # cancel a running build
jeeves --format json build list my-pipeline  # structured output for scripting
jeeves build rebuild my-pipeline             # re-run lastBuild with its parameters
jeeves build rebuild my-pipeline --param ENV=staging   # ...overriding one of them
```

## Nodes

```bash
jeeves node list                 # online/offline, executors, labels
jeeves node list --stats         # + disk, temp, swap, response time, architecture
jeeves node list --address       # + each agent's launcher host/IP
jeeves --format json node list --stats   # raw byte/ms values for scripting
```

## Lockable resources

Lockable resources are not part of base Jenkins — they come from the
[`lockable-resources`](https://plugins.jenkins.io/lockable-resources/) plugin,
so these commands live under the `plugin` group. On a Jenkins without the
plugin they all decline politely rather than failing obscurely.

```bash
jeeves plugin lockable-resources list                      # the whole register
jeeves plugin lockable-resources list --state locked       # only what a build holds
jeeves plugin lockable-resources list --label db --label prod   # both labels required
jeeves plugin lockable-resources show staging-db           # one resource, in full

jeeves plugin lockable-resources reserve staging-db --reason "schema migration"
jeeves plugin lockable-resources unreserve staging-db      # release your own reservation
jeeves plugin lockable-resources unlock staging-db         # release a build's lock
jeeves plugin lockable-resources reset staging-db          # clear locks, reservations and queue

jeeves plugin lockable-resources add rig-02 --description "spare rig" --label hardware
jeeves plugin lockable-resources remove rig-02             # prompts first on a terminal
jeeves plugin lockable-resources remove rig-02 --yes       # ...or do not
```

Every verb is idempotent: a resource already in the state you asked for says so
and exits 0, so these are safe to put in a script.

```console
$ jeeves plugin lockable-resources reserve staging-db
🎩 'staging-db' is presently in the hands of bertie, sir. One does not simply take it.

$ jeeves plugin lockable-resources list
🎩 The Lockable Resources plugin does not appear to be installed on this Jenkins, sir. Without it there are no resources for me to attend to.
```

Reserving, releasing and creating each need their own Jenkins permission
(`RESERVE`, `UNLOCK` and `CONFIGURE` respectively), and releasing a reservation
is restricted to its holder or an administrator.

## Config file

```bash
jeeves --init-config       # write ~/.config/jeeves/config.toml
jeeves --show-config       # print resolved config
jeeves --config my.toml    # use a custom config file
```

## Connection profiles

Target multiple Jenkins servers from one config file. See
[docs/manual/options.md](options.md) for the `[profiles.NAME]` schema and
precedence rules.

```bash
jeeves --profile prod status                 # use a named profile for one command
JEEVES_PROFILE=staging jeeves job list       # env alternative to the flag
```

## Managing profiles

```bash
jeeves profile list                             # table; tokens masked
jeeves profile add prod --url https://ci.prod --username me --token -
jeeves profile add prod --token - --force       # rotate just the token
jeeves profile use prod                         # set default-profile
jeeves profile use --clear                      # back to the flat keys
jeeves profile remove staging                   # delete a profile
```

## Shell completions

```bash
eval "$(jeeves completions bash)"   # bash
eval "$(jeeves completions zsh)"    # zsh
jeeves completions fish | source    # fish
```

## Caching

```bash
jeeves --cache                      # enable caching
jeeves --cache --cache-ttl 10m      # cache for 10 minutes
jeeves --no-cache                   # disable caching
```
