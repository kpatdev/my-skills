# delegate-agent

Portable Agent Skill for delegating bounded work to an independent coding-agent harness — a subagent that runs outside the calling agent's context, on a different model, and hands back a report.

Delegates: Google Antigravity CLI, Claude Code, OpenAI Codex CLI, OpenCode, Pi Coding Agent.

## Install

```bash
npx skills add kpatdev/skills -s delegate-agent
npx skills update
```

`scripts/install.sh` is the older path: it copies the skill to `~/.agents/skills/delegate-agent` (discovered directly by Codex, OpenCode, and Pi) and symlinks `~/.claude/skills/delegate-agent` to that copy. Because it copies, an existing install does not track new commits, and it refuses to overwrite — remove the copy before re-running.

## Check delegates

```bash
~/.agents/skills/delegate-agent/scripts/delegate-agent list
```

## Examples

```bash
# Adversarial verification of a specific claim
scripts/delegate-agent run codex --role verify \
  --task "Claim to falsify: the retry guard in src/queue.ts cannot double-enqueue." --cwd "$PWD"

# Independent root-cause investigation
scripts/delegate-agent run claude --role debug \
  --task "tests/integration/socket_test.py hangs on roughly 1 run in 20. Find the root cause." --cwd "$PWD"

# A bounded change, with checks
scripts/delegate-agent run codex --role implement \
  --task "Add the missing retry guard described in src/queue.ts:88, with tests." --cwd "$PWD"

# Fan out to every installed harness
scripts/delegate-agent all --role review \
  --task "Review the proposed migration in db/migrations/0042 for breaking assumptions." --cwd "$PWD"
```

## Roles

`review`, `verify`, `debug`, `research`, `solve`, `implement`.

Everything except `implement` defaults to read-only; `--write` and `--read-only` override. Parallel write-mode fanout to one checkout is blocked — use a `git worktree` per writer.

## Models

`--model` for a single delegate, `--models agent=model,...` for a fanout, or a named profile from `config.example.json` copied to `~/.config/delegate-agent/config.json` or `<repo>/.delegate-agent.json`.

```bash
scripts/delegate-agent models          # what each installed CLI can report
scripts/delegate-agent run codex --role verify --task "..." --dry-run
```

## Output

Each delegate's answer lands in the calling agent's context, so `--max-output-chars` (default 60000, `0` disables) bounds it, eliding the middle and keeping both ends. It is the budget for the whole run: a fanout splits it across delegates. `elided_chars` reports what was dropped.

A delegate that hits `--timeout` (default 900s) is killed as a process group, so nothing the harness spawned outlives it.

## Requirements

Python 3, and whichever delegate CLIs you want, installed and authenticated. No third-party Python dependencies.

`SKILL.md` is the agent-facing document; `references/adapters.md` covers per-harness isolation and model selection.

## Tests

```bash
python3 -m unittest discover -s tests
```
