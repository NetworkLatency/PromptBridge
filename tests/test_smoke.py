from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from promptbridge.gateway.orchestrator import PromptBridgeOrchestrator


class PromptBridgeSmokeTest(unittest.TestCase):
    def test_compile_search_and_dream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = PromptBridgeOrchestrator(Path(tmp) / "workspace")
            orchestrator.init_workspace()

            compile_result = orchestrator.compile("我想优化 Context Kernel 和工具成本")
            self.assertTrue(compile_result.prompt_path.exists())
            self.assertIn("PromptBridge Execution Prompt", compile_result.compiled_prompt.text)
            self.assertGreaterEqual(len(compile_result.retrieval.hits), 1)

            search_result = orchestrator.search_memory("工具成本")
            self.assertGreaterEqual(len(search_result.hits), 1)

            patch = orchestrator.dream("promptbridge")
            self.assertTrue(patch.path.exists())
            self.assertIn("MemoryPatch Proposal", patch.text)

    def test_cli_plugin_target_package(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            orchestrator = PromptBridgeOrchestrator(Path(tmp) / "workspace")
            result = orchestrator.compile(
                "我想优化 MCP 工具加载策略",
                target="cli-plugin",
            )

            self.assertEqual(result.target_package.target, "cli-plugin")
            self.assertIsNotNone(result.target_package.artifact_path)
            self.assertTrue(result.target_package.artifact_path.exists())
            self.assertEqual(result.translation_result.provider, "none")


if __name__ == "__main__":
    unittest.main()
