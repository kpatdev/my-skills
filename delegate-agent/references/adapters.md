# Adapters, isolation, and models

The per-harness branch of [`SKILL.md`](../SKILL.md): what each delegate actually guarantees, and how to point one at a specific model. `--dry-run` prints the exact command for any combination, so use it rather than reconstructing invocations from this page.

## Isolation

Read-only mode means something different in each harness. The wrapper always states the constraint in the prompt as well, but a prompt is a request and a sandbox is not — this column is what actually holds.

| Target | Executable | Read-only enforcement | Write mode |
|---|---|---|---|
| Antigravity | `agy` | `--mode=plan` — read-only tools before proposing changes | `--mode=accept-edits`; Antigravity's own permission and sandbox settings still apply |
| Claude Code | `claude` | `--permission-mode plan` | `--permission-mode auto` — deliberately not `bypassPermissions`, so permission checks stay live |
| Codex | `codex` | `--sandbox read-only --ask-for-approval never` — an OS sandbox, the strongest guarantee here | `--sandbox workspace-write`, still never escalating |
| OpenCode | `opencode` | `run --agent plan` — the built-in analysis agent | `run --agent build --auto`; local config can override agent permissions |
| Pi | `pi` | `-p --tools read,grep,find,ls` — a tool allowlist, no OS sandbox | full tool set, running as the launching user |

Pi is the one to watch: with no sandbox of its own, a write-mode Pi delegate has the permissions of the account that launched it. Put it in a container or a throwaway worktree when the isolation has to be real.

A delegate that hits `--timeout` is killed as an entire process group, so the model requests and test runners the harness spawned die with it. The timeout bounds the work, not merely the wait.

`all` runs the selected harnesses concurrently, three at a time by default (`--parallel`). Write-mode fanout to a single checkout is blocked outright, because concurrent writers to one working tree corrupt each other's edits — one `git worktree` and one `--cwd` per writer.

`--max-output-chars` is the whole run's output budget, not each delegate's: a fanout divides it across the delegates, so five harnesses cannot spend five times the caller's context.

## Models

`run` takes `--model`; `all` takes `--models agent=model,...`, because model identifiers are not portable across harnesses. A universal `--model` still applies to every agent in a fanout, and is mostly useful when the same provider slug works everywhere.

```sh
scripts/delegate-agent all --agents claude,codex,pi \
  --models 'claude=CLAUDE_ALIAS,codex=CODEX_ID,pi=PROVIDER/MODEL' \
  --role verify --task "..."
```

For discovery, `scripts/delegate-agent models` shells out to `agy models`, `opencode models`, and `pi --list-models`. Claude Code and Codex both accept `--model` but expose their catalogs through interactive pickers and account configuration, so the wrapper returns selection guidance for those two instead of guessing.

## Profiles

Reusable model sets live in JSON, read from the first source that exists: `--config PATH`, then `<cwd>/.delegate-agent.json`, then `~/.config/delegate-agent/config.json`. `--profile NAME` selects one; `default_profile` applies when no `--profile` is given. Command-line `--model` and `--models` win over both.

See [`config.example.json`](../config.example.json) for the shape.

## Why the wrapper normalizes stdout

Every harness exposes a one-shot headless text mode, and those stay stable. Their native JSON does not — one returns a single object, another streams JSONL lifecycle events, another emits session and tool events with no stable final-result object. The wrapper therefore captures each harness's final text and returns an envelope it owns, keeping native stderr separate for diagnostics.
