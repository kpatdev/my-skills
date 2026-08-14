---
name: delegate-agent
description: Delegate a bounded task to an independent coding-agent harness — Antigravity, Claude Code, Codex, OpenCode, or Pi — and treat what comes back as evidence. Use when the user names one of those harnesses, wants a second opinion from a different model, wants the current work adversarially verified, wants an independent root-cause investigation, or wants several harnesses compared in parallel.
---

# Delegate Agent

Treat every delegate answer as **evidence**: brief a bounded task, run it in the narrowest mode that can answer it, corroborate its material claims at the source, and keep the conclusion the parent's own.

Delegates: `antigravity` (`agy`), `claude`, `codex`, `opencode`, `pi`.

## Establish the delegate surface

Run:

```sh
scripts/delegate-agent list
scripts/delegate-agent run --help
```

Resolve `scripts/delegate-agent` relative to this file; under Claude Code, `${CLAUDE_SKILL_DIR}/scripts/delegate-agent` reaches it from any install location.

`list` reports each harness's executable and whether it is on PATH. The installed set is the source of truth — a harness named here but absent from `list` cannot run, so choose from what `list` returns. This step is complete when the installed harnesses and every flag the run needs are visible.

## Choose the delegate

Delegate when independence buys something the parent cannot supply itself:

- the user names a harness or asks another agent to look;
- an independent second opinion would change the parent's confidence;
- a hard bug deserves a root-cause investigation that starts from the symptoms rather than from the parent's current hypothesis;
- the parent's own implementation or conclusion should be attacked;
- several plausible architectures should be developed separately and compared;
- a bounded research question can leave this conversation without taking context with it.

Independence is the whole return on the cost, so pick a harness different from the parent — a delegate running the parent's own model rediscovers the same blind spots. When the user names a harness, use the one they named.

Send one delegate by default. Send a second only when an independent counterexample is worth the cost, which is mostly hard debugging and verification. Use `all` when the user asks for broad comparison or consensus across harnesses.

This step is complete when the chosen harness appears installed in `list`, and either differs from the parent or was named by the user.

## Choose the role

`--role` becomes the delegate's marching orders, so it shapes the answer more than the task wording does.

| Role | The delegate's job | Default mode |
|---|---|---|
| `review` | Critique code or design, weighting correctness, security, maintainability, and test gaps over style | read-only |
| `verify` | Attack a stated claim — hunt counterexamples, edge cases, missing tests, false assumptions | read-only |
| `debug` | Diagnose root cause independently, with competing hypotheses and the smallest credible fix | read-only |
| `research` | Answer a bounded technical question, separating verified fact from inference | read-only |
| `solve` | Develop an alternative solution or plan from the requirements | read-only |
| `implement` | Make a bounded change, run the relevant checks, report what changed | workspace-write |

`--read-only` and `--write` override the default when a role needs the other mode.

## Brief the task

`--task` is everything the delegate gets — it starts cold, with no access to this conversation. Include the objective, the files or symptoms to start from, the constraints, the evidence already gathered, and the shape of the answer wanted.

Two roles want the parent's own thinking handled differently: `verify` needs the parent's claim stated plainly so there is something to falsify, while `solve` produces a genuine alternative only when the parent's approach is left out of the brief.

The brief is complete when an agent with no access to this conversation could act on it without asking a question.

## Run in the narrowest mode

```sh
scripts/delegate-agent run codex --role verify \
  --task "Claim to falsify: the token refresh in src/auth/refresh.ts is safe under concurrent 401s. Find an interleaving that double-refreshes." --cwd "$PWD"

scripts/delegate-agent all --agents claude,codex,pi --role debug \
  --task "tests/integration/socket_test.py hangs on roughly 1 run in 20. Find the root cause." --cwd "$PWD"
```

`--dry-run` prints the exact command without running it — reach for it when a flag or model identifier is uncertain. Omitting `--agents` fans out to every installed harness.

Read-only is the default for every role but `implement`, and it is what makes fanout safe. Write mode takes one writer per checkout: parallel write fanout is blocked, so give each writer its own `git worktree` and its own `--cwd`.

For per-harness model identifiers, reusable profiles, and the isolation each harness actually provides, read [`references/adapters.md`](references/adapters.md) before selecting a model or running in write mode.

## Corroborate the result

`result` holds the delegate's final text. `ok`, `exit_code`, and `stderr` describe the run, not the answer — a harness exits 0 with a confident wrong conclusion as readily as it exits non-zero having produced a usable partial one. Read both, and treat a truncated or empty `result` as a failed delegation rather than a finding.

Then, before the delegate's framing sets:

1. Separate its claims from its conclusion.
2. Check each claim the parent will rely on against the repository, the tests, the logs, or authoritative docs. A cited file path, line number, or test result is a claim until the parent has seen it.
3. Settle disagreement between delegates on evidence, so a majority of harnesses repeating one plausible error stays outvoted by the repository.
4. State the parent's own conclusion, naming any part that still rests on an unverified delegate claim.

A `verify` delegation earns its cost by returning a counterexample, a missing test, a false assumption, or an explicit account of what was checked and found sound; an unsupported "looks fine" means the task was too loose, and is worth re-running with a sharper claim to falsify.

The delegation is complete when every material claim the parent relies on has been checked at its source and the parent has stated its own conclusion.
