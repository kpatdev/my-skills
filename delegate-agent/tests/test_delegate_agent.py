#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
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

    def test_read_only_prompt_states_the_constraint(self):
        prompt = mod.build_prompt("t", "verify", False, pathlib.Path("/tmp"))
        self.assertIn("READ-ONLY MODE", prompt)
        self.assertIn("non-mutating", prompt)
        self.assertIn("WRITE MODE", mod.build_prompt("t", "implement", True, pathlib.Path("/tmp")))


if __name__ == "__main__":
    unittest.main()
