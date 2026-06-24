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

## Working with builds

```bash
jeeves builds summary my-pipeline            # last / successful / failed builds
jeeves builds list my-pipeline               # recent build history
jeeves builds list my-pipeline --limit 50 --result FAILURE
jeeves builds show my-pipeline 142           # a specific build
jeeves --format json builds list my-pipeline # structured output for scripting
jeeves params my-pipeline                    # list the job's build parameters
jeeves build my-pipeline --param ENV=prod
jeeves rebuild my-pipeline                   # re-run lastBuild with its parameters
jeeves rebuild my-pipeline --param ENV=staging   # ...overriding one of them
```

## Config file

```bash
jeeves --init-config       # write ~/.config/jeeves/config.toml
jeeves --show-config       # print resolved config
jeeves --config my.toml    # use a custom config file
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
