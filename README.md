# skills

Agent Skills — documents that teach a coding agent to operate a specific tool or workflow reliably.

Each skill is a folder with a `SKILL.md` the agent loads, plus any reference files, scripts, and adapters it needs. They are written to be portable across harnesses rather than tied to one.

| Skill | What it does |
|---|---|
| [`codexbar`](codexbar) | Meter AI subscription usage through the CodexBar CLI — quota headroom, reset times, runway forecasts, cost attribution, and headroom gates for scripts and CI. |
| [`delegate-agent`](delegate-agent) | Delegate bounded work to another coding-agent harness (Antigravity, Claude Code, Codex, OpenCode, Pi) as a subagent running outside the caller's context. |
| [`memo`](memo) | Operate Apple Notes and Apple Reminders through the memo CLI, treating every indexed change as an attended transaction. |
| [`short-form-video`](short-form-video) | Write and critique short-form video scripts for a pharmacy's social media — hook, authority, story, and a close sized to the viewer's trust. |

## Install

```sh
npx skills add kpatdev/skills
```

That detects your agents and installs all four skills. Pick up later changes with:

```sh
npx skills update
```

`add` symlinks into your agent directories rather than copying, which is what makes `update` a one-liner. Useful variations:

```sh
npx skills add kpatdev/skills -l                 # list what's here, install nothing
npx skills add kpatdev/skills -s delegate-agent  # a single skill
npx skills add kpatdev/skills -g                 # user-level; default is project-level
npx skills list                                  # what's installed
npx skills remove                                # uninstall interactively
```

### From a checkout

When editing the skills themselves, symlink the working copy so edits are live without reinstalling:

```sh
ln -s "$PWD/memo" ~/.agents/skills/memo   # Codex, OpenCode, and Pi read this
ln -s "$PWD/memo" ~/.claude/skills/memo   # Claude Code reads its own directory
```

`delegate-agent` also ships `scripts/install.sh`, predating the above. It *copies* to `~/.agents/skills/delegate-agent` and links Claude Code's directory to that copy, so an existing install will not pick up new commits — and it refuses to overwrite, so remove the copy before re-running. Prefer `npx skills`.

## Writing a skill

The house style, visible across all four:

- **A leading word up front.** Each skill opens by naming the discipline it enforces — an *attended transaction* for `memo`, a *live snapshot* for `codexbar`, a *subagent in another harness* for `delegate-agent`, the *cold viewer* for `short-form-video` — and the rest of the document anchors to it.
- **The environment is the source of truth.** Skills start by running `--help` against the installed binary rather than restating flags that will drift. What they cache is what the tooling cannot confess: unwritten conventions, failure modes, and the reasoning behind a choice.
- **Every step ends on a completion criterion.** A step says how the agent can tell done from not-done, so it cannot drift off mid-task believing it finished.
- **Progressive disclosure.** Material only some runs need lives in a reference file behind a pointer, keeping the main document short enough to stay legible.
- **Positive instructions.** Skills state the target behavior rather than banning the wrong one; a prohibition drags the forbidden behavior into context and makes it more available, not less.
- **Invocation matched to reach.** The three tool skills carry model-facing descriptions so an agent fires them on its own. `short-form-video` sets `disable-model-invocation: true` — it only ever runs when you type its name, so it costs no context load.

These follow the `writing-for-agents` skill, which is where the reasoning behind them lives.

## Tests

`delegate-agent` carries a test suite:

```sh
cd delegate-agent && python3 -m unittest discover -s tests
```
