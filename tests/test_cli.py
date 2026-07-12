from __future__ import annotations

from contextlib import redirect_stderr
import io
import unittest

from promptbridge.cli import build_parser


class CliContractTest(unittest.TestCase):
    def test_compile_has_no_prompt_or_response_language_option(self) -> None:
        args = build_parser().parse_args(["compile", "Review this architecture."])
        self.assertFalse(hasattr(args, "to"))

        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            build_parser().parse_args(
                ["compile", "Review this architecture.", "--to", "Japanese"]
            )


if __name__ == "__main__":
    unittest.main()
