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
```

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
eval "$(jeeves --completion bash)"   # bash
eval "$(jeeves --completion zsh)"    # zsh
jeeves --completion fish | source    # fish
```

## Caching

```bash
jeeves --cache                      # enable caching
jeeves --cache --cache-ttl 10m      # cache for 10 minutes
jeeves --no-cache                   # disable caching
```
