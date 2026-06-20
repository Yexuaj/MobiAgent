from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runner.mobiagent.personal_intelligence.load_workflow_run import load_workflow_run
from runner.mobiagent.personal_intelligence.normalize_events import normalize_workflow_run


class RawEventsImportTest(unittest.TestCase):
    def test_windows_absolute_screenshot_path_normalization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-run"
            screenshot_path = run_dir / "steps" / "2" / "home_before_swipe.jpg"
            screenshot_path.parent.mkdir(parents=True)
            screenshot_path.write_bytes(b"fake image")
            self._write_summary(run_dir, image_path=str(screenshot_path))

            record = load_workflow_run(run_dir=run_dir)
            raw_events = normalize_workflow_run(record, project_root=project_root)

        artifacts = [artifact for event in raw_events["events"] for artifact in event["artifacts"]]
        self.assertEqual(raw_events["schema_version"], "pi.raw_events.v1")
        self.assertEqual(raw_events["artifact_base"]["path"], "outputs/personal_intelligence/raw_runs/unit-run")
        self.assertEqual(artifacts[0]["path"], "steps/2/home_before_swipe.jpg")
        self.assertNotIn("\\", artifacts[0]["path"])
        self.assertNotIn("path_type", artifacts[0])

    def test_raw_step_is_omitted_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-run"
            self._write_summary(run_dir)

            record = load_workflow_run(run_dir=run_dir)
            raw_events = normalize_workflow_run(record, project_root=project_root)

        self.assertTrue(raw_events["events"])
        self.assertTrue(all("raw_step" not in event for event in raw_events["events"]))

    def test_include_raw_step(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-run"
            self._write_summary(run_dir)

            record = load_workflow_run(run_dir=run_dir)
            raw_events = normalize_workflow_run(record, include_raw_step=True, project_root=project_root)

        self.assertTrue(raw_events["events"])
        self.assertTrue(all("raw_step" in event for event in raw_events["events"]))

    def test_summary_outside_run_dir_adds_warning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-run"
            summary_dir = project_root / "fixtures"
            summary_path = summary_dir / "external_summary.json"
            self._write_summary(summary_dir, summary_name="external_summary.json")

            record = load_workflow_run(run_dir=run_dir, summary_path=summary_path)
            raw_events = normalize_workflow_run(record, project_root=project_root)

        self.assertEqual(raw_events["artifact_base"]["path"], "outputs/personal_intelligence/raw_runs/unit-run")
        self.assertEqual(raw_events["run_summary_path"], "fixtures/external_summary.json")
        self.assertIn("run_summary_path_warning", raw_events)

    def _write_summary(self, run_dir: Path, *, summary_name: str = "run_summary.json", image_path: str | None = None) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        output = {"action": "screenshot", "device": "Android"}
        if image_path is not None:
            output["image_path"] = image_path
        summary = {
            "workflow_file": "runner/mobiagent/personal_intelligence/examples/workflows/android_smoke_workflow.json",
            "run_dir": str(run_dir),
            "context": {},
            "steps": {
                "2": {
                    "step_id": "2",
                    "status": "success",
                    "started_at": 1.0,
                    "finished_at": 2.0,
                    "duration_sec": 1.0,
                    "output": output,
                    "error": None,
                }
            },
            "status": "success",
        }
        with (run_dir / summary_name).open("w", encoding="utf-8") as file:
            json.dump(summary, file)


if __name__ == "__main__":
    unittest.main()
