# Getting Started with five-clis

This guide walks you through everything you need to do after clicking **Use this template**
on GitHub — from renaming the package to watching your first green CI run.

## 1. Create your repo from the template

On the [five-clis GitHub page](https://github.com/mrsixw/five-clis), click
**Use this template → Create a new repository**. Give it a name (this becomes your CLI
name, e.g. `myapp`).

## 2. Clone and install dependencies

```bash
git clone https://github.com/<you>/<myapp>
cd <myapp>
uv sync --extra dev
```

Verify everything works before you change anything:

```bash
make format && make lint && make test
```

## 3. Rename the package

Run the interactive rename script — it handles all find/replace, renames the source
directory, and removes stale build artefacts in one pass:

```bash
uv run python utils/rename.py
```

You'll be prompted for three values:

| Prompt | Example | What it sets |
| ------ | ------- | ------------ |
| Python package name | `myapp` | `src/fiveclis/` → `src/myapp/`, imports |
| CLI binary name | `my-app` | Entry point, Makefile, CI, completions |
| GitHub repo | `you/myapp` | `install.sh`, `updater.py`, CI badge |

If you prefer to rename manually, see the full file-by-file reference table in the
[five-clis README](https://github.com/mrsixw/five-clis#using-this-template).

## 4. Replace the demo business logic

`src/<pkg>/cli.py` contains a `greet` demo command. Replace the section marked
`# ── Business logic (replace this section) ──` with your own logic. Keep the
surrounding infrastructure (themes, config, caching, update check) as-is.

## 5. Add the `GH_TOKEN` secret

The release CI job creates GitHub releases and pushes version tags. It needs a
Personal Access Token (PAT) with write access — the auto-provided `GITHUB_TOKEN`
doesn't have enough scope for this step.

**Create a PAT:**

1. Go to **GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens**
2. Click **Generate new token**
3. Set **Resource owner** to your account (or org)
4. Under **Repository access**, select your new repo
5. Under **Permissions → Repository permissions**, grant **Contents: Read and write**
6. Click **Generate token** and copy the value

**Add it as a secret:**

1. Go to your repo: **Settings → Secrets and variables → Actions**
2. Click **New repository secret**
3. Name: `GH_TOKEN`
4. Value: paste the PAT you just created
5. Click **Add secret**

Without this secret the `release` CI job will fail with:
`Error: Input required and not supplied: token`

## 6. Validate locally

```bash
make format && make lint && make test
```

All three must exit clean before you push.

## 7. Push and watch CI

```bash
git add -A
git commit -m "feat: initial <myapp> CLI"
git push -u origin main
```

Open **Actions** in your repo. You should see all jobs go green. The `release` job
runs only on pushes to `main` (excluding version-bump commits), so your first push
will trigger a release automatically.

## What a green first run looks like

| Job | What it checks |
| --- | -------------- |
| `test` | pytest suite |
| `lint` | ruff + black |
| `spell` | typos across all files |
| `docs-lint` | markdownlint on docs |
| `build` | shiv binary compiles |
| `man` | man page generates and compresses |
| `completions` | bash/zsh/fish scripts generated and valid |
| `release` | version bump, binary + man + completions attached, `gh release create` |
| `verify-release` | installs from the published release and checks `--version` |
