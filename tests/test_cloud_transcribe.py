from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "cloud_transcribe.py"
SPEC = importlib.util.spec_from_file_location("cloud_transcribe", MODULE_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class CloudTranscribeTests(unittest.TestCase):
    def test_format_timestamp(self) -> None:
        self.assertEqual(MODULE.format_timestamp(0), "00:00:00")
        self.assertEqual(MODULE.format_timestamp(3661.4), "01:01:01")

    def test_keywords_are_deduplicated(self) -> None:
        self.assertEqual(
            MODULE.sanitize_keywords([" 黄芪 ", "黄芪", "# comment", "白芍"]),
            ["黄芪", "白芍"],
        )

    def test_keywords_reject_angle_brackets(self) -> None:
        with self.assertRaises(ValueError):
            MODULE.sanitize_keywords(["<黄芪>"])

    def test_prompt_includes_previous_tail_only_when_present(self) -> None:
        self.assertEqual(MODULE.build_prompt(), MODULE.DEFAULT_PROMPT)
        prompt = MODULE.build_prompt("上一段结尾")
        self.assertIn("上一段结尾", prompt)


if __name__ == "__main__":
    unittest.main()

