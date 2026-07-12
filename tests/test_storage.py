from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import io
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from promptbridge.cli import main
from promptbridge.storage import AppPaths, CleanupPlan, StorageGroup, StorageMaintenance


class StorageMaintenanceTest(unittest.TestCase):
    def test_status_does_not_create_a_missing_home(self) -> None:
        with TemporaryDirectory() as temporary:
            home = Path(temporary) / "missing"

            status = StorageMaintenance(AppPaths(home)).status()

            self.assertFalse(status.home_exists)
            self.assertEqual(status.total_files, 0)
            self.assertFalse(home.exists())

    def test_cleanup_removes_only_old_managed_groups(self) -> None:
        with TemporaryDirectory() as temporary:
            paths = AppPaths(Path(temporary) / ".promptbridge")
            paths.ensure()
            paths.providers_file.write_text('{"profiles": []}\n', encoding="utf-8")

            old_trace = _write(paths.traces_dir / "trace_old.json", "{}\n")
            old_prompt = _write(paths.artifacts_dir / "trace_old.prompt.md", "old prompt\n")
            old_response = _write(paths.artifacts_dir / "trace_old.response.md", "old response\n")
            orphan = _write(paths.artifacts_dir / "trace_orphan.prompt.md", "orphan\n")
            recent_trace = _write(paths.traces_dir / "trace_recent.json", "{}\n")
            recent_prompt = _write(paths.artifacts_dir / "trace_recent.prompt.md", "recent\n")
            unknown_artifact = _write(paths.artifacts_dir / "notes.txt", "keep\n")
            unknown_trace = _write(paths.traces_dir / "README.txt", "keep\n")

            now = datetime(2026, 7, 12, tzinfo=timezone.utc)
            _set_modified((old_trace, old_prompt, old_response, orphan), now - timedelta(days=60))
            _set_modified((recent_trace, recent_prompt), now - timedelta(days=5))

            storage = StorageMaintenance(paths)
            status = storage.status()
            self.assertEqual(status.managed_groups, 3)
            self.assertEqual(status.orphan_artifacts, 1)
            self.assertEqual(status.unmanaged_files, 2)

            plan = storage.cleanup_plan(30, now=now)
            self.assertEqual({group.trace_id for group in plan.groups}, {"trace_old", "trace_orphan"})
            self.assertEqual(plan.files, 4)

            result = storage.apply(plan)
            self.assertEqual(result.deleted_files, 4)
            for path in (old_trace, old_prompt, old_response, orphan):
                self.assertFalse(path.exists())
            for path in (recent_trace, recent_prompt, unknown_artifact, unknown_trace):
                self.assertTrue(path.exists())
            self.assertTrue(paths.providers_file.exists())
            self.assertTrue(paths.glossary_file.exists())

            forged_plan = CleanupPlan(
                cutoff=now,
                groups=(
                    StorageGroup(
                        trace_id="trace_forged",
                        paths=(unknown_artifact,),
                        modified_at=now - timedelta(days=60),
                        has_trace=False,
                    ),
                ),
            )
            with self.assertRaisesRegex(ValueError, "unmanaged"):
                storage.apply(forged_plan)
            self.assertTrue(unknown_artifact.exists())

    def test_cli_clean_is_dry_run_until_apply_is_explicit(self) -> None:
        with TemporaryDirectory() as temporary:
            home = Path(temporary) / ".promptbridge"
            paths = AppPaths(home)
            paths.ensure()
            trace = _write(paths.traces_dir / "trace_old.json", "{}\n")
            _set_modified((trace,), datetime.now(timezone.utc) - timedelta(days=45))

            output = io.StringIO()
            with redirect_stdout(output):
                return_code = main(["--home", str(home), "storage", "clean", "--older-than", "30"])

            self.assertEqual(return_code, 0)
            self.assertTrue(trace.exists())
            self.assertIn("dry-run", output.getvalue())
            self.assertIn("No files deleted", output.getvalue())

            with redirect_stdout(io.StringIO()):
                return_code = main(
                    ["--home", str(home), "storage", "clean", "--older-than", "30", "--apply"]
                )

            self.assertEqual(return_code, 0)
            self.assertFalse(trace.exists())


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _set_modified(paths: tuple[Path, ...], value: datetime) -> None:
    timestamp = value.timestamp()
    for path in paths:
        os.utime(path, (timestamp, timestamp))


if __name__ == "__main__":
    unittest.main()
