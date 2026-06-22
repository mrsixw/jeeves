# Usage Guide

## Basic usage

```bash
jeeves
jeeves --name Alice
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
