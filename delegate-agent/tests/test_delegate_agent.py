#!/usr/bin/env python3
import importlib.util
import os
import pathlib
import shutil
import subprocess
import sys
import time
import unittest

MODULE_PATH = pathlib.Path(__file__).parents[1] / "scripts" / "delegate_agent.py"
spec = importlib.util.spec_from_file_location("delegate_agent", MODULE_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = mod
assert spec.loader
spec.loader.exec_module(mod)


class DelegateAgentTests(unittest.TestCase):
    def test_roles_default_read_only(self):
        for role in mod.READ_ONLY_ROLES:
            self.assertFalse(mod.resolve_mode(role, False, False), role)
        self.assertTrue(mod.resolve_mode("implement", False, False))

    def test_antigravity_modes(self):
        ro = mod.adapter_command("antigravity", "x", False, None)
        wr = mod.adapter_command("antigravity", "x", True, None)
        self.assertIn("--mode=plan", ro)
        self.assertIn("--mode=accept-edits", wr)

    def test_codex_sandbox(self):
        ro = mod.adapter_command("codex", "x", False, None)
        wr = mod.adapter_command("codex", "x", True, None)
        self.assertIn("read-only", ro)
        self.assertIn("workspace-write", wr)
        self.assertIn("never", ro)

    def test_pi_read_tools(self):
        ro = mod.adapter_command("pi", "x", False, None)
        joined = " ".join(ro)
        self.assertIn("read,grep,find,ls", joined)

    def test_opencode_agents(self):
        ro = mod.adapter_command("opencode", "x", False, None)
        wr = mod.adapter_command("opencode", "x", True, None)
        self.assertIn("plan", ro)
        self.assertIn("build", wr)

    def test_parse_agents_deduplicates(self):
        self.assertEqual(mod.parse_agents("claude,codex,claude"), ["claude", "codex"])

    def test_parse_model_map(self):
        self.assertEqual(
            mod.parse_model_map("claude=opus,codex=gpt-x,pi=anthropic/model"),
            {"claude": "opus", "codex": "gpt-x", "pi": "anthropic/model"},
        )

    def test_profile_models(self):
        config = {"profiles": {"quality": {"claude": "opus", "codex": "gpt-x"}}}
        self.assertEqual(
            mod.profile_models(config, "quality"),
            {"claude": "opus", "codex": "gpt-x"},
        )

    def test_model_is_forwarded(self):
        for agent in mod.SUPPORTED:
            cmd = mod.adapter_command(agent, "x", False, "model-x")
            self.assertIn("--model", cmd, agent)
            self.assertIn("model-x", cmd, agent)

    def test_installed_agents_are_a_supported_subset(self):
        try:
            names = mod.installed_agents()
        except ValueError:
            return  # no harness on PATH; the error path is the documented behavior
        self.assertTrue(set(names).issubset(set(mod.SUPPORTED)))
        for name in names:
            self.assertTrue(mod.command_exists(mod.ADAPTERS[name].executable), name)

    def test_elide_keeps_both_ends_within_budget(self):
        text = "HEAD" + ("x" * 5000) + "TAIL"
        kept, removed = mod.elide(text, 500)
        self.assertLessEqual(len(kept), 500)
        self.assertTrue(kept.startswith("HEAD"), "conclusion sits at the head of a delegate answer")
        self.assertTrue(kept.endswith("TAIL"), "next actions sit at the tail")
        self.assertIn(f"{removed} characters elided", kept)
        # Everything not elided is still present, so the counter is honest.
        marker = f"\n\n[... {removed} characters elided by delegate-agent ...]\n\n"
        self.assertEqual(len(kept) - len(marker) + removed, len(text))

    def test_elide_leaves_short_text_alone(self):
        self.assertEqual(mod.elide("short", 500), ("short", 0))
        self.assertEqual(mod.elide("anything", 0), ("anything", 0))

    def test_normalized_result_reports_elisions(self):
        payload = mod.normalized_result(
            agent="codex", role="verify", writable=False, cwd=pathlib.Path("/tmp"),
            cmd=["codex"], ok=True, exit_code=0,
            result="y" * 10_000, stderr="", duration=1.0, max_output=1000,
        )
        self.assertLessEqual(len(payload["result"]), 1000)
        self.assertGreater(payload["elided_chars"]["result"], 0)
        self.assertEqual(payload["elided_chars"]["stderr"], 0)

    def test_uncapped_output_is_passed_through(self):
        payload = mod.normalized_result(
            agent="codex", role="verify", writable=False, cwd=pathlib.Path("/tmp"),
            cmd=["codex"], ok=True, exit_code=0,
            result="y" * 10_000, stderr="", duration=1.0, max_output=0,
        )
        self.assertEqual(len(payload["result"]), 10_000)
        self.assertEqual(payload["elided_chars"]["result"], 0)

    @unittest.skipUnless(os.name == "posix" and shutil.which("pgrep"), "needs posix + pgrep")
    def test_kill_process_tree_reaps_grandchildren(self):
        # A harness spawns model requests and test runners of its own; killing
        # only the direct child leaves those burning tokens after a timeout.
        marker = "sleep 31339"
        proc = subprocess.Popen(
            ["sh", "-c", f"{marker} & {marker}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        try:
            time.sleep(1)
            running = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split()
            self.assertTrue(running, "probe failed to start")

            mod.kill_process_tree(proc)
            proc.communicate()
            time.sleep(1)
            survivors = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split()
            self.assertEqual(survivors, [], "orphaned descendants survived the kill")
        finally:
            for pid in subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True).stdout.split():
                subprocess.run(["kill", "-9", pid], capture_output=True)

    def test_read_only_prompt_states_the_constraint(self):
        prompt = mod.build_prompt("t", "verify", False, pathlib.Path("/tmp"))
        self.assertIn("READ-ONLY MODE", prompt)
        self.assertIn("non-mutating", prompt)
        self.assertIn("WRITE MODE", mod.build_prompt("t", "implement", True, pathlib.Path("/tmp")))


if __name__ == "__main__":
    unittest.main()
