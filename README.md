# skills

Agent Skills — documents that teach a coding agent to operate a specific tool or workflow reliably.

Each skill is a folder with a `SKILL.md` the agent loads, plus any reference files, scripts, and adapters it needs. They are written to be portable across harnesses rather than tied to one.

| Skill | What it does |
|---|---|
| [`codexbar`](codexbar) | Meter AI subscription usage through the CodexBar CLI — quota headroom, reset times, runway forecasts, cost attribution, and headroom gates for scripts and CI. |
| [`delegate-agent`](delegate-agent) | Delegate bounded work to another coding-agent harness (Antigravity, Claude Code, Codex, OpenCode, Pi) as a subagent running outside the caller's context. |
| [`memo`](memo) | Operate Apple Notes and Apple Reminders through the memo CLI, treating every indexed change as an attended transaction. |

## Install

Skills are discovered by directory. Copy or symlink the ones you want into the locations your harnesses read:

```sh
# Codex, OpenCode, and Pi discover this directly
ln -s "$PWD/memo" ~/.agents/skills/memo

# Claude Code reads its own directory
ln -s "$PWD/memo" ~/.claude/skills/memo
```

Symlinking from a checkout keeps the installed skill current as the repo changes.

`delegate-agent` ships an installer instead, because it carries scripts of its own. It *copies* the skill to `~/.agents/skills/delegate-agent` and points `~/.claude/skills/delegate-agent` at that copy, so pulling new commits does not update it — remove the copy and re-run to upgrade, since the installer refuses to overwrite an existing install:

```sh
./delegate-agent/scripts/install.sh
```

## Writing a skill

The house style, visible across all three:

- **A leading word up front.** Each skill opens by naming the discipline it enforces — an *attended transaction* for `memo`, a *live snapshot* for `codexbar`, a *subagent in another harness* for `delegate-agent` — and the rest of the document anchors to it.
- **The environment is the source of truth.** Skills start by running `--help` against the installed binary rather than restating flags that will drift. What they cache is what the tooling cannot confess: unwritten conventions, failure modes, and the reasoning behind a choice.
- **Every step ends on a completion criterion.** A step says how the agent can tell done from not-done, so it cannot drift off mid-task believing it finished.
- **Progressive disclosure.** Material only some runs need lives in a reference file behind a pointer, keeping the main document short enough to stay legible.
- **Positive instructions.** Skills state the target behavior rather than banning the wrong one; a prohibition drags the forbidden behavior into context and makes it more available, not less.

These follow the `writing-for-agents` skill, which is where the reasoning behind them lives.

## Tests

`delegate-agent` carries a test suite:

```sh
cd delegate-agent && python3 -m unittest discover -s tests
```
