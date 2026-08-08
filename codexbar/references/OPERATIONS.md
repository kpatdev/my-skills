# CodexBar operations

Read only the section for the requested branch.

## Cost and attribution

Use the cost meter to inspect local token history:

```sh
codexbar cost --provider codex --format json --pretty --json-only
codexbar cost --provider codex --days 30 --group-by project --format json --pretty --json-only
```

Use `--refresh` when the user needs a current rescan rather than cached results. Report `sessionTokens`, `sessionCostUSD`, the selected history window, model or project hotspots, and `historyCoverageIsEstablished` when present. Label all dollar values as estimates unless the provider supplies a native billed amount.

Cost is evidence about local activity, not subscription headroom. This branch is complete when the time range, source coverage, and largest contributors are explicit.

## Measure a work session

Capture usage JSON immediately before and after the work. Compare only snapshots with the same provider, account, source, quota-window duration, and reset timestamp. For each unchanged lane, subtract the first `usedPercent` from the second and report the elapsed wall time.

If a reset or account/source change occurred, the delta is not comparable; report the boundary and keep the two snapshots separate. Pair the quota delta with `codexbar cost` only when the user also wants local token or cost attribution.

This branch is complete when every compared lane shares the same reset epoch and scope, and every rejected comparison names the mismatch.

## Choose a provider or account

Collect machine-readable usage across enabled providers:

```sh
codexbar usage --provider all --format json --pretty --json-only --status
codexbar usage --provider codex --all-accounts --format json --pretty --json-only
```

For a quick human-readable overview when analysis is unnecessary, prefer `codexbar cards --brief --provider all --no-color` when installed help supports it.

For each candidate, compare the short and long quota lanes, native pace projection, service status, source freshness, credits, and fetch errors. Prefer the candidate whose bottleneck survives the requested horizon; use raw remaining percentage only when no pace result exists. Present the tradeoff and leave any account or provider switch to the user's requested workflow.

This branch is complete when every candidate is either compared on the same requested horizon or excluded with a concrete reason.

## Diagnose stale or failed data

Work from least invasive evidence:

1. Capture `codexbar --version`, the failed command, exit status, stdout, and stderr.
2. Run `codexbar config validate --format json --pretty --json-only` when supported.
3. Retry one provider with `--status`; distinguish provider outage from credential, source, parse, or timeout failure.
4. Inspect `codexbar usage --help` and the provider's upstream documentation, then force `--source web|cli|oauth|api` only when that source is supported and isolating it answers the diagnosis.
5. Use verbose or JSONL logs only as needed, redacting account identifiers, paths, tokens, and cookie material before sharing them.

Cache clearing and cookie refresh change local state. Stage those commands under the authorization rule in `SKILL.md`; prefer a refresh path whose help promises to preserve the old credential on failure.

Diagnosis is complete when the failure is assigned to a specific layer or the remaining unknown is bounded by observed command output.

## Automate gates, snapshots, and alerts

Use `codexbar guard` for a Boolean quota gate instead of parsing display text. Keep unavailable quota distinct from insufficient quota by preserving its exit code and structured decision.

Use one-shot JSON for dashboards and artifacts when supported:

```sh
codexbar dashboard --pretty
```

Add `--identity redacted` when installed help supports it. Otherwise filter account identity before saving or sharing the payload. A dashboard snapshot may contain healthy and failed provider rows while exiting successfully, so inspect row-level errors.

For a local live dashboard, bind `codexbar serve` to loopback. Treat a non-loopback bind as a network exposure: require the user's explicit request, a bearer token supplied by environment variable, the installed version's security flags, and disclosure of whether transport is encrypted. Compare `/health`'s version with `codexbar --version` after upgrades.

For transition-driven alerts, inspect `codexbar hooks --help`, `codexbar hooks list`, and the upstream hook configuration contract. Hook configuration changes and `hooks test` require authorization because tests execute matching external commands. Run `hooks watch` as one continuous process so its in-memory transition baseline survives between polls.

Automation is complete when its output contract, identity exposure, failure policy, process lifetime, and verification probe are all explicit.
