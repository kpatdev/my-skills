#!/usr/bin/env python3
"""Portable multi-harness delegation wrapper.

Uses only the Python standard library. It intentionally normalizes the *final
stdout* from each harness instead of depending on vendor-specific JSON schemas,
which change more often than their documented headless text modes.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SUPPORTED = ("antigravity", "claude", "codex", "opencode", "pi")
READ_ONLY_ROLES = {"review", "verify", "debug", "research", "solve"}
ROLES = tuple(sorted(READ_ONLY_ROLES | {"implement"}))

ROLE_INSTRUCTIONS = {
    "review": "Critique the supplied code/design. Prioritize concrete correctness, security, maintainability, and test gaps over stylistic preferences.",
    "verify": "Act adversarially. Try to falsify the parent conclusion or implementation. Look for counterexamples, edge cases, missing tests, and invalid assumptions.",
    "debug": "Investigate independently. Identify the most likely root cause, supporting evidence, competing hypotheses, and the smallest credible fix.",
    "research": "Investigate the bounded technical question. Distinguish verified facts from inference and cite repository evidence or authoritative sources available to you.",
    "solve": "Develop an independent solution or implementation plan. Derive the approach from the workspace and the stated requirements.",
    "implement": "Implement the bounded requested change. Keep the patch focused, run relevant checks, and report exactly what changed and what remains uncertain.",
}

@dataclass(frozen=True)
class Adapter:
    name: str
    executable: str

ADAPTERS = {
    "antigravity": Adapter("antigravity", "agy"),
    "claude": Adapter("claude", "claude"),
    "codex": Adapter("codex", "codex"),
    "opencode": Adapter("opencode", "opencode"),
    "pi": Adapter("pi", "pi"),
}

# Harnesses with stable non-interactive model-list commands. Others still accept
# --model but expose selection primarily through interactive pickers/docs.
MODEL_LIST_COMMANDS = {
    "antigravity": ["agy", "models"],
    "opencode": ["opencode", "models"],
    "pi": ["pi", "--list-models"],
}

MODEL_LIST_GUIDANCE = {
    "claude": "Claude Code accepts --model; use /model interactively or Anthropic's model configuration docs to see recognized aliases/IDs.",
    "codex": "Codex accepts --model; use the current Codex models documentation/configuration for supported model IDs.",
}


def command_exists(name: str) -> bool:
    return shutil.which(name) is not None


def build_prompt(task: str, role: str, writable: bool, cwd: Path) -> str:
    access = (
        "WRITE MODE: Edit files inside the workspace as this bounded task requires. "
        "Keep every effect inside this checkout: no pushes, publishes, deploys, or history rewrites."
        if writable
        else
        "READ-ONLY MODE: Inspect the workspace and run non-mutating checks only. "
        "Leave every file, dependency, commit, and remote exactly as you found it."
    )

    if role == "implement":
        return_format = (
            "Return: (1) concise conclusion, (2) files changed and why, (3) tests/checks run with results, "
            "(4) risks or unresolved issues."
        )
    else:
        return_format = (
            "Return: (1) concise conclusion, (2) specific evidence with file paths/locations or commands where useful, "
            "(3) risks/counterarguments, (4) recommended next action."
        )

    return f"""You are an independent delegated coding agent.

ROLE: {role.upper()}
ROLE INSTRUCTION: {ROLE_INSTRUCTIONS[role]}
WORKSPACE: {cwd}

{access}

OBJECTIVE:
{task.strip()}

Reach your own conclusion from the workspace; treat the parent agent's view as a claim to test. Stay within the stated objective.
{ return_format }
"""


def adapter_command(agent: str, prompt: str, writable: bool, model: str | None) -> list[str]:
    """Build a conservative headless invocation for each harness."""
    if agent == "antigravity":
        cmd = ["agy", "-p", prompt, "--output-format", "text"]
        cmd += ["--mode=accept-edits" if writable else "--mode=plan"]
        if model:
            cmd += ["--model", model]
        return cmd

    if agent == "claude":
        # plan is read-only; auto is safer for autonomous implementation than bypassPermissions.
        cmd = [
            "claude", "-p", prompt,
            "--output-format", "text",
            "--permission-mode", "auto" if writable else "plan",
            "--no-session-persistence",
        ]
        if model:
            cmd += ["--model", model]
        return cmd

    if agent == "codex":
        cmd = [
            "codex", "exec",
            "--sandbox", "workspace-write" if writable else "read-only",
            "--ask-for-approval", "never",
        ]
        if model:
            cmd += ["--model", model]
        cmd += [prompt]
        return cmd

    if agent == "opencode":
        cmd = [
            "opencode", "run",
            "--agent", "build" if writable else "plan",
        ]
        if writable:
            cmd += ["--auto"]
        if model:
            cmd += ["--model", model]
        cmd += [prompt]
        return cmd

    if agent == "pi":
        cmd = ["pi", "-p"]
        if not writable:
            # Pi has no built-in sandbox; restrict the available tools for read-only roles.
            cmd += ["--tools", "read,grep,find,ls"]
        if model:
            cmd += ["--model", model]
        cmd += [prompt]
        return cmd

    raise ValueError(f"Unsupported agent: {agent}")


def normalized_result(
    *, agent: str, role: str, writable: bool, cwd: Path,
    cmd: list[str], ok: bool, exit_code: int | None,
    result: str, stderr: str, duration: float, error: str | None = None,
    dry_run: bool = False, model: str | None = None,
) -> dict:
    return {
        "agent": agent,
        "role": role,
        "mode": "workspace-write" if writable else "read-only",
        "model": model,
        "cwd": str(cwd),
        "ok": ok,
        "exit_code": exit_code,
        "duration_seconds": round(duration, 3),
        "result": result.strip(),
        "stderr": stderr.strip(),
        "error": error,
        "dry_run": dry_run,
        "command": shlex.join(cmd) if dry_run else None,
    }


def run_one(
    agent: str,
    role: str,
    task: str,
    cwd: Path,
    writable: bool,
    model: str | None,
    timeout: int,
    dry_run: bool,
) -> dict:
    adapter = ADAPTERS[agent]
    prompt = build_prompt(task, role, writable, cwd)
    cmd = adapter_command(agent, prompt, writable, model)

    if dry_run:
        return normalized_result(
            agent=agent, role=role, writable=writable, cwd=cwd, cmd=cmd,
            ok=True, exit_code=0, result="", stderr="", duration=0.0,
            dry_run=True, model=model,
        )

    if not command_exists(adapter.executable):
        return normalized_result(
            agent=agent, role=role, writable=writable, cwd=cwd, cmd=cmd,
            ok=False, exit_code=None, result="", stderr="", duration=0.0,
            error=f"Executable not found: {adapter.executable}", model=model,
        )

    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            stdin=subprocess.DEVNULL,  # a harness that falls back to an interactive prompt must fail, not block
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            env=os.environ.copy(),
            check=False,
        )
        duration = time.monotonic() - start
        return normalized_result(
            agent=agent,
            role=role,
            writable=writable,
            cwd=cwd,
            cmd=cmd,
            ok=(proc.returncode == 0),
            exit_code=proc.returncode,
            result=proc.stdout,
            stderr=proc.stderr,
            duration=duration,
            error=None if proc.returncode == 0 else f"{agent} exited with code {proc.returncode}",
            model=model,
        )
    except subprocess.TimeoutExpired as exc:
        duration = time.monotonic() - start
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        return normalized_result(
            agent=agent, role=role, writable=writable, cwd=cwd, cmd=cmd,
            ok=False, exit_code=None, result=stdout, stderr=stderr, duration=duration,
            error=f"Timed out after {timeout} seconds", model=model,
        )
    except Exception as exc:  # wrapper should report failures, not hide them
        duration = time.monotonic() - start
        return normalized_result(
            agent=agent, role=role, writable=writable, cwd=cwd, cmd=cmd,
            ok=False, exit_code=None, result="", stderr="", duration=duration,
            error=f"{type(exc).__name__}: {exc}", model=model,
        )


def resolve_mode(role: str, force_write: bool, force_read_only: bool) -> bool:
    if force_write and force_read_only:
        raise ValueError("--write and --read-only are mutually exclusive")
    if force_write:
        return True
    if force_read_only:
        return False
    return role == "implement"


def parse_agents(value: str) -> list[str]:
    names = []
    for part in value.split(","):
        name = part.strip().lower()
        if not name:
            continue
        if name not in SUPPORTED:
            raise ValueError(f"Unsupported agent '{name}'. Supported: {', '.join(SUPPORTED)}")
        if name not in names:
            names.append(name)
    if not names:
        raise ValueError("No agents selected")
    return names


def installed_agents() -> list[str]:
    """Default fanout set: fanning out to an uninstalled harness only manufactures failures."""
    names = [name for name in SUPPORTED if command_exists(ADAPTERS[name].executable)]
    if not names:
        raise ValueError(
            f"No supported harness found on PATH. Install one of: {', '.join(SUPPORTED)}"
        )
    return names


def parse_model_map(value: str | None) -> dict[str, str]:
    """Parse agent=model pairs, comma-separated."""
    if not value:
        return {}
    result: dict[str, str] = {}
    for part in value.split(","):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Invalid model mapping '{item}'. Expected agent=model")
        agent, model = item.split("=", 1)
        agent = agent.strip().lower()
        model = model.strip()
        if agent not in SUPPORTED:
            raise ValueError(f"Unsupported agent '{agent}' in --models")
        if not model:
            raise ValueError(f"Empty model for agent '{agent}'")
        result[agent] = model
    return result


def load_config(cwd: Path, explicit_path: str | None) -> tuple[dict, Path | None]:
    """Load model-profile config. Project config wins over user config unless --config is explicit."""
    candidates: list[Path] = []
    if explicit_path:
        candidates = [Path(explicit_path).expanduser()]
    else:
        candidates = [
            cwd / ".delegate-agent.json",
            Path.home() / ".config" / "delegate-agent" / "config.json",
        ]

    for path in candidates:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read config {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"Config must contain a JSON object: {path}")
        return data, path
    if explicit_path:
        raise ValueError(f"Config file not found: {candidates[0]}")
    return {}, None


def resolve_profile(config: dict, requested: str | None) -> str | None:
    return requested or config.get("default_profile")


def profile_models(config: dict, profile: str | None) -> dict[str, str]:
    if not profile:
        return {}
    profiles = config.get("profiles", {})
    if not isinstance(profiles, dict) or profile not in profiles:
        raise ValueError(f"Unknown model profile '{profile}'")
    mapping = profiles[profile]
    if not isinstance(mapping, dict):
        raise ValueError(f"Profile '{profile}' must be an object mapping agent names to model IDs")
    result: dict[str, str] = {}
    for agent, model in mapping.items():
        if agent not in SUPPORTED:
            raise ValueError(f"Unsupported agent '{agent}' in profile '{profile}'")
        if not isinstance(model, str) or not model.strip():
            raise ValueError(f"Profile '{profile}' model for '{agent}' must be a non-empty string")
        result[agent] = model.strip()
    return result


def emit(payload: object, pretty: bool = True) -> None:
    print(json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False))


def add_common_run_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--role", choices=ROLES, default="solve")
    parser.add_argument("--task", required=True, help="Self-contained task for the delegate")
    parser.add_argument("--cwd", default=os.getcwd(), help="Workspace directory (default: current directory)")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--write", action="store_true", help="Allow workspace edits")
    mode.add_argument("--read-only", action="store_true", help="Force read-only behavior")
    parser.add_argument("--model", help="Harness-specific model identifier; overrides profile selection")
    parser.add_argument("--profile", help="Named model profile from .delegate-agent.json or ~/.config/delegate-agent/config.json")
    parser.add_argument("--config", help="Explicit path to model-profile config JSON")
    parser.add_argument("--timeout", type=int, default=900, help="Per-agent timeout in seconds (default: 900)")
    parser.add_argument("--dry-run", action="store_true", help="Print normalized payload with exact command; do not execute")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="delegate-agent",
        description="Delegate a bounded task to an independent coding-agent harness.",
    )
    sub = parser.add_subparsers(dest="subcommand", required=True)

    p_list = sub.add_parser("list", help="List supported harnesses and whether their CLI is installed")
    p_list.add_argument("--compact", action="store_true")

    p_models = sub.add_parser("models", help="Show locally discoverable models or selection guidance")
    p_models.add_argument("agent", nargs="?", choices=SUPPORTED, help="Optional harness; defaults to all")
    p_models.add_argument("--timeout", type=int, default=20, help="Per-command timeout in seconds")

    p_run = sub.add_parser("run", help="Run one delegated agent")
    p_run.add_argument("agent", choices=SUPPORTED)
    add_common_run_args(p_run)

    p_all = sub.add_parser("all", help="Run selected delegated agents in parallel")
    p_all.add_argument("--agents", help="Comma-separated agents (default: every supported harness installed on PATH)")
    p_all.add_argument("--models", help="Per-agent model map: antigravity=MODEL,claude=MODEL,codex=MODEL,...")
    p_all.add_argument("--parallel", type=int, default=3, help="Maximum concurrent delegates (default: 3)")
    add_common_run_args(p_all)

    args = parser.parse_args(argv)

    if args.subcommand == "list":
        rows = [
            {
                "agent": name,
                "executable": ADAPTERS[name].executable,
                "installed": command_exists(ADAPTERS[name].executable),
                "path": shutil.which(ADAPTERS[name].executable),
            }
            for name in SUPPORTED
        ]
        emit(rows, pretty=not args.compact)
        return 0

    if args.subcommand == "models":
        selected = [args.agent] if args.agent else list(SUPPORTED)
        rows = []
        for agent in selected:
            adapter = ADAPTERS[agent]
            if not command_exists(adapter.executable):
                rows.append({"agent": agent, "installed": False, "ok": False, "models": None, "guidance": "CLI not installed"})
                continue
            cmd = MODEL_LIST_COMMANDS.get(agent)
            if not cmd:
                rows.append({"agent": agent, "installed": True, "ok": True, "models": None, "guidance": MODEL_LIST_GUIDANCE[agent]})
                continue
            try:
                proc = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=args.timeout, check=False)
                rows.append({
                    "agent": agent,
                    "installed": True,
                    "ok": proc.returncode == 0,
                    "command": shlex.join(cmd),
                    "models": proc.stdout.strip() or None,
                    "stderr": proc.stderr.strip() or None,
                })
            except subprocess.TimeoutExpired:
                rows.append({"agent": agent, "installed": True, "ok": False, "models": None, "guidance": f"Model listing timed out after {args.timeout}s"})
        emit(rows)
        return 0 if all(row["ok"] for row in rows) else 1

    cwd = Path(args.cwd).expanduser().resolve()
    if not cwd.exists() or not cwd.is_dir():
        emit({"ok": False, "error": f"Workspace is not a directory: {cwd}"})
        return 2
    if args.timeout <= 0:
        emit({"ok": False, "error": "--timeout must be greater than zero"})
        return 2

    try:
        config, config_path = load_config(cwd, args.config)
        profile = resolve_profile(config, args.profile)
        profile_map = profile_models(config, profile)
    except ValueError as exc:
        emit({"ok": False, "error": str(exc)})
        return 2

    try:
        writable = resolve_mode(args.role, args.write, args.read_only)
    except ValueError as exc:
        emit({"ok": False, "error": str(exc)})
        return 2

    if args.subcommand == "run":
        selected_model = args.model or profile_map.get(args.agent)
        payload = run_one(
            args.agent, args.role, args.task, cwd, writable, selected_model, args.timeout, args.dry_run
        )
        payload["profile"] = profile
        payload["config"] = str(config_path) if config_path else None
        emit(payload)
        return 0 if payload["ok"] else 1

    try:
        agents = parse_agents(args.agents) if args.agents else installed_agents()
        per_agent_models = parse_model_map(args.models)
    except ValueError as exc:
        emit({"ok": False, "error": str(exc)})
        return 2

    if args.parallel <= 0:
        emit({"ok": False, "error": "--parallel must be greater than zero"})
        return 2

    if writable and len(agents) > 1:
        emit({
            "ok": False,
            "error": (
                "Parallel write-mode delegation to one checkout is intentionally blocked. "
                "Create a separate Git worktree per writer and run each agent separately with its own --cwd."
            ),
        })
        return 2

    results: list[dict] = []
    workers = min(args.parallel, len(agents))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(
                run_one, agent, args.role, args.task, cwd, writable,
                per_agent_models.get(agent) or args.model or profile_map.get(agent), args.timeout, args.dry_run
            ): agent
            for agent in agents
        }
        for future in concurrent.futures.as_completed(future_map):
            results.append(future.result())

    results.sort(key=lambda x: agents.index(x["agent"]))
    payload = {
        "ok": all(item["ok"] for item in results),
        "role": args.role,
        "mode": "workspace-write" if writable else "read-only",
        "agents": agents,
        "profile": profile,
        "config": str(config_path) if config_path else None,
        "models": {agent: (per_agent_models.get(agent) or args.model or profile_map.get(agent)) for agent in agents},
        "results": results,
    }
    emit(payload)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
