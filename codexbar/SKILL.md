---
name: codexbar
description: Meter AI subscription usage with the CodexBar CLI. Use when the user asks how much Codex or another provider quota remains, when a limit resets, whether usage will last through a session, what recent token costs were, which provider or account has headroom, whether a CodexBar-tracked provider is degraded, or asks for CodexBar quota gates, hooks, dashboards, or troubleshooting.
---

# CodexBar

Treat every answer as a **live snapshot**: query the installed binary, preserve provider and account scope, name the source and freshness, and separate measurements from forecasts.

## Establish the command surface

Run:

```sh
command -v codexbar
codexbar --version
codexbar --help
codexbar usage --help
```

Run `<command> --help` for every other command the request needs. CodexBar changes quickly; the installed help is the source of truth. Use the current [upstream CLI reference](https://github.com/steipete/CodexBar/blob/main/docs/cli.md) only to resolve missing context or a version mismatch.

If the executable is absent, stop with the official installation choices from the upstream reference and resume after the user chooses one. This step is complete when the executable, version, required commands, and required flags are all visible.

## Take the snapshot

For a Codex quota or runway question, run:

```sh
codexbar usage --provider codex --format json --pretty --json-only
```

Substitute the provider the user named; use Codex only when the request identifies Codex or the current Codex session.

From JSON, account for:

- provider, account identity, plan, login method, resolved `source`, provider/client `version`, and `usage.updatedAt`;
- every non-null quota window's `usedPercent`, remaining headroom (`100 - usedPercent`), `windowMinutes`, and `resetsAt`;
- each available `pace` result, including `willLastToReset`, `etaSeconds`, `runOutProbability`, and `summary`;
- credits or extra usage separately from subscription windows, preserving the reported label and unit;
- provider status when the user asks about an outage or anomalous result; rerun with `--status`.

Summarize account identifiers rather than reproducing full emails unless the identity disambiguates accounts. A snapshot is complete when the requested scope and every relevant lane are visible, or each unavailable field is named as unavailable.

## Forecast runway

For Codex and Claude, the primary/session lane is the provider's short quota window, not the lifetime of the current conversation. The secondary/weekly lane can become the binding limit first.

Interpret each native pace result:

- `willLastToReset: true` means the lane is projected to survive until reset at the modeled pace.
- `willLastToReset: false` with `etaSeconds` means the lane is projected to empty in that interval.
- A non-null `runOutProbability` is a risk estimate; present it as probability, not certainty.
- A missing pace result means there is no defensible forecast from this snapshot. Report headroom and reset time without inventing an ETA.

Compare every quota lane. A currently exhausted lane is the bottleneck. When every relevant lane has a pace result, call the earliest projected exhaustion the bottleneck; if all will reach reset, report **no bottleneck projected before reset** and identify the lane with the least current headroom as the tightest lane. When any non-exhausted lane lacks pace, report **bottleneck unknown** because that lane cannot be forecast, then give every known ETA and the tightest observed lane. If the user supplied a work-session duration, compare it with every pre-reset exhaustion ETA; if the horizon crosses a reset, bound the conclusion to that reset. Otherwise report the known forecast horizon and treat a duration as optional follow-up context.

Use quota windows for subscription depletion; `codexbar cost` is a separate meter of local token-cost estimates. A runway answer is complete when it states remaining headroom, reset, pace outcome, bottleneck outcome, freshness, and the forecast's limitation.

## Gate work on headroom

Use the native guard for scripts, CI, or a preflight reserve check:

```sh
codexbar guard --provider codex --window session --min-remaining 20 --json --pretty
codexbar guard --provider codex --window weekly --min-remaining 10 --json --pretty
```

Capture the exit status. Current stable meanings are `0` safe, `1` below threshold, `64` invalid arguments, and `69` unavailable; confirm them in installed help. Check both lanes when either could stop the work. Choose fail-closed by omitting `--fail-open`; add it only when the user's automation policy explicitly treats an unavailable meter as safe.

A gate is complete when every required lane has a recorded threshold, decision, reason, and exit status.

## Reach the specialized branch

For cost attribution, provider/account selection, start/end burn measurement, status or authentication diagnosis, hooks, dashboards, or serving, read [`references/OPERATIONS.md`](references/OPERATIONS.md) before running that branch.

## Control effects and report

Use read-only commands for inspection. Treat configuration edits, API-key storage, cache clearing, cookie refresh, hook enable/disable/test, dashboard file output, and server startup as stateful operations. Before one, inspect the target, show the exact command with secrets represented by environment-variable names, explain the material effect, and get explicit user authorization. Verify the intended postcondition afterward.

Keep credentials out of arguments, output, and final answers. Prefer stdin or environment variables supported by installed help, and avoid printing a raw config that may contain secrets.

Lead the final answer with the decision the snapshot supports. Include the provider/account scope, remaining percentage for each binding lane, reset time, projected runway, data timestamp/source, and any unavailable or failed fetches.
