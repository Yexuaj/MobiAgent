from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from runner.mobiagent.personal_intelligence.cli import main as cli_main
from runner.mobiagent.personal_intelligence.ingest.visual_text_adapter import (
    PROVIDER_WORKFLOW_VLM_QA_OUTPUT,
    build_visual_text_inputs,
)
from runner.mobiagent.personal_intelligence.load_workflow_run import load_workflow_run
from runner.mobiagent.personal_intelligence.normalize_events import normalize_workflow_run


class VisualTextProviderTest(unittest.TestCase):
    def test_visual_text_is_disabled_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-visual"
            output_path = project_root / "semantic_out" / "semantic_events.json"
            visible_text = "Synthetic demo todo prepare report tomorrow 3pm"
            self._write_visual_summary(run_dir, structured_output={"visible_text": visible_text})

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(["run-pipeline", "--run-dir", str(run_dir), "--out", str(output_path)])

            self.assertEqual(exit_code, 0)
            with output_path.open("r", encoding="utf-8") as file:
                semantic_events = json.load(file)

        self.assertTrue(all(event["content"]["text"] is None for event in semantic_events["events"]))
        self.assertNotIn(visible_text, json.dumps(semantic_events, ensure_ascii=False))
        self._assert_no_visual_leaks(json.dumps(semantic_events, ensure_ascii=False))

    def test_workflow_vlm_qa_output_maps_visible_text_to_screenshot_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-visual"
            output_path = project_root / "semantic_out" / "semantic_events.json"
            visible_text = "Synthetic dashboard says prepare Android report tomorrow 3pm"
            self._write_visual_summary(run_dir, structured_output={"visible_text": visible_text})

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(
                    [
                        "run-pipeline",
                        "--run-dir",
                        str(run_dir),
                        "--out",
                        str(output_path),
                        "--enable-visual-text",
                        "--visual-text-provider",
                        PROVIDER_WORKFLOW_VLM_QA_OUTPUT,
                    ]
                )

            self.assertEqual(exit_code, 0)
            with output_path.open("r", encoding="utf-8") as file:
                semantic_events = json.load(file)

        screenshot_event = self._event_by_source_id(semantic_events, "step:1")
        vlm_event = self._event_by_source_id(semantic_events, "step:2")
        provenance = screenshot_event["content"]["provenance"]

        self.assertEqual(screenshot_event["content"]["text"], visible_text)
        self.assertIsNone(vlm_event["content"]["text"])
        self.assertEqual(provenance["kind"], "workflow_vlm_qa")
        self.assertEqual(provenance["provider"], PROVIDER_WORKFLOW_VLM_QA_OUTPUT)
        self.assertEqual(provenance["source_field"], "output.structured_output.visible_text")
        self.assertEqual(provenance["source_artifact_id"], "step:1:artifact:1")
        self.assertFalse(provenance["synthetic"])
        self.assertTrue(semantic_events["derived"]["todo_candidates"])
        self.assertTrue(semantic_events["derived"]["time_hints"])
        self._assert_no_visual_leaks(json.dumps(semantic_events, ensure_ascii=False))

    def test_workflow_vlm_qa_output_uses_fallback_fields(self) -> None:
        cases = [
            ({"page_summary": "Synthetic page summary mentions MobiAgent"}, "output.page_summary"),
            ({"response": "Synthetic response mentions Android"}, "output.response"),
            (
                {"structured_output": {"summary": "Synthetic structured summary mentions WeChat"}},
                "output.structured_output.summary",
            ),
        ]
        for output_extra, expected_field in cases:
            with self.subTest(expected_field=expected_field), tempfile.TemporaryDirectory() as tmp_dir:
                project_root = Path(tmp_dir) / "project"
                run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-visual"
                self._write_visual_summary(run_dir, **output_extra)

                record = load_workflow_run(run_dir=run_dir)
                raw_events = normalize_workflow_run(record, project_root=project_root)
                visual_inputs = build_visual_text_inputs(record, raw_events)

            self.assertEqual(list(visual_inputs.text_inputs), ["step:1"])
            self.assertEqual(visual_inputs.text_provenance_inputs["step:1"]["source_field"], expected_field)
            self.assertEqual(
                visual_inputs.text_provenance_inputs["step:1"]["source_artifact_id"],
                "step:1:artifact:1",
            )

    def test_visual_text_max_events_and_max_chars_limit_injected_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-visual"
            output_path = project_root / "semantic_out" / "semantic_events.json"
            first_text = "Synthetic first dashboard prepare report tomorrow 3pm"
            second_text = "Synthetic second dashboard follow up next week"
            self._write_visual_summary(
                run_dir,
                structured_output={"visible_text": first_text},
                extra_visual_steps=[(3, 4, second_text)],
            )

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(
                    [
                        "run-pipeline",
                        "--run-dir",
                        str(run_dir),
                        "--out",
                        str(output_path),
                        "--enable-visual-text",
                        "--visual-text-max-events",
                        "1",
                        "--visual-text-max-chars",
                        "24",
                    ]
                )

            self.assertEqual(exit_code, 0)
            with output_path.open("r", encoding="utf-8") as file:
                semantic_events = json.load(file)

        first_screenshot_event = self._event_by_source_id(semantic_events, "step:1")
        second_screenshot_event = self._event_by_source_id(semantic_events, "step:3")

        self.assertEqual(first_screenshot_event["content"]["text"], first_text[:24])
        self.assertIsNone(second_screenshot_event["content"]["text"])
        self.assertNotIn(second_text, json.dumps(semantic_events, ensure_ascii=False))
        self._assert_no_visual_leaks(json.dumps(semantic_events, ensure_ascii=False))

    def test_workflow_vlm_qa_output_falls_back_to_previous_screenshot_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-visual"
            visible_text = "Synthetic fallback text prepare handoff tomorrow"
            self._write_visual_summary(
                run_dir,
                structured_output={"visible_text": visible_text},
                image_ref=None,
            )

            record = load_workflow_run(run_dir=run_dir)
            raw_events = normalize_workflow_run(record, project_root=project_root)
            visual_inputs = build_visual_text_inputs(record, raw_events)

        self.assertEqual(visual_inputs.text_inputs, {"step:1": visible_text})
        self.assertEqual(
            visual_inputs.text_provenance_inputs["step:1"]["source_artifact_id"],
            "step:1:artifact:1",
        )

    def test_workflow_vlm_qa_output_skips_text_when_no_screenshot_event_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-visual"
            output_path = project_root / "semantic_out" / "semantic_events.json"
            visible_text = "Synthetic orphan visual text should not enter semantics"
            self._write_visual_summary(
                run_dir,
                structured_output={"visible_text": visible_text},
                include_screenshot=False,
                image_ref=None,
            )

            record = load_workflow_run(run_dir=run_dir)
            raw_events = normalize_workflow_run(record, project_root=project_root)
            visual_inputs = build_visual_text_inputs(record, raw_events)

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(
                    [
                        "run-pipeline",
                        "--run-dir",
                        str(run_dir),
                        "--out",
                        str(output_path),
                        "--enable-visual-text",
                    ]
                )

            self.assertEqual(exit_code, 0)
            with output_path.open("r", encoding="utf-8") as file:
                semantic_events = json.load(file)

        self.assertEqual(visual_inputs.text_inputs, {})
        self.assertEqual(visual_inputs.text_provenance_inputs, {})
        self.assertTrue(all(event["content"]["text"] is None for event in semantic_events["events"]))
        self.assertNotIn(visible_text, json.dumps(semantic_events, ensure_ascii=False))
        self._assert_no_visual_leaks(json.dumps(semantic_events, ensure_ascii=False))

    def test_visual_text_debug_report_has_no_raw_or_path_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-visual"
            output_path = project_root / "semantic_out" / "semantic_events.json"
            report_path = project_root / "semantic_out" / "weekly_report.md"
            self._write_visual_summary(
                run_dir,
                structured_output={"visible_text": "Synthetic visible text says follow up MobiAgent next week"},
            )

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(
                    [
                        "run-pipeline",
                        "--run-dir",
                        str(run_dir),
                        "--out",
                        str(output_path),
                        "--enable-visual-text",
                        "--report-out",
                        str(report_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            with output_path.open("r", encoding="utf-8") as file:
                semantic_events = json.load(file)
            report = report_path.read_text(encoding="utf-8")

        self.assertIn("Personal Intelligence Local Baseline/Debug Report", report)
        self.assertIn(
            "This report is generated from local baseline extraction for contract validation and demo review. "
            "It is not a final user-facing intelligence report.",
            report,
        )
        for section in ("Highlights", "Possible Tasks", "Time References", "Context Notes", "Evidence"):
            self.assertIn(f"## {section}", report)
        self._assert_no_visual_leaks(json.dumps(semantic_events, ensure_ascii=False) + report)

    def _write_visual_summary(
        self,
        run_dir: Path,
        *,
        structured_output: dict | None = None,
        page_summary: str | None = None,
        summary: str | None = None,
        response: str | None = None,
        image_ref: str | None = "${steps.1.output.image_path}",
        include_screenshot: bool = True,
        extra_visual_steps: list[tuple[int, int, str]] | None = None,
    ) -> None:
        screenshot_path = run_dir / "steps" / "1" / "synthetic_demo_page.jpg"
        if include_screenshot:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            screenshot_path.write_bytes(b"synthetic screenshot bytes")
        run_dir.mkdir(parents=True, exist_ok=True)

        vlm_output: dict = {
            "tool_name": "vlm_qa",
            "inputs": {},
        }
        if image_ref is not None:
            vlm_output["inputs"]["image"] = image_ref
        if structured_output is not None:
            vlm_output["structured_output"] = structured_output
        if page_summary is not None:
            vlm_output["page_summary"] = page_summary
        if summary is not None:
            vlm_output["summary"] = summary
        if response is not None:
            vlm_output["response"] = response
        vlm_output["raw_output_debug"] = {
            "image_path": str(screenshot_path),
            "device": "Android",
        }

        summary_data = {
            "workflow_file": "runner/mobiagent/personal_intelligence/examples/workflows/android_vlm_qa_synthetic_demo.json",
            "run_dir": str(run_dir),
            "context": {},
            "steps": {},
            "status": "success",
        }
        if include_screenshot:
            summary_data["steps"]["1"] = {
                "step_id": "1",
                "status": "success",
                "started_at": 1.0,
                "finished_at": 1.5,
                "duration_sec": 0.5,
                "output": {"image_path": str(screenshot_path), "device": "Android"},
                "error": None,
            }
        summary_data["steps"]["2"] = {
            "step_id": "2",
            "status": "success",
            "started_at": 2.0,
            "finished_at": 3.0,
            "duration_sec": 1.0,
            "tool_name": "vlm_qa",
            "inputs": dict(vlm_output["inputs"]),
            "output": vlm_output,
            "error": None,
        }
        for screenshot_step, vlm_step, visible_text in extra_visual_steps or []:
            extra_screenshot_path = run_dir / "steps" / str(screenshot_step) / "synthetic_demo_page.jpg"
            extra_screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            extra_screenshot_path.write_bytes(b"synthetic screenshot bytes")
            summary_data["steps"][str(screenshot_step)] = {
                "step_id": str(screenshot_step),
                "status": "success",
                "started_at": float(screenshot_step),
                "finished_at": float(screenshot_step) + 0.5,
                "duration_sec": 0.5,
                "output": {"image_path": str(extra_screenshot_path), "device": "Android"},
                "error": None,
            }
            extra_image_ref = f"${{steps.{screenshot_step}.output.image_path}}"
            summary_data["steps"][str(vlm_step)] = {
                "step_id": str(vlm_step),
                "status": "success",
                "started_at": float(vlm_step),
                "finished_at": float(vlm_step) + 1.0,
                "duration_sec": 1.0,
                "tool_name": "vlm_qa",
                "inputs": {"image": extra_image_ref},
                "output": {
                    "tool_name": "vlm_qa",
                    "inputs": {"image": extra_image_ref},
                    "structured_output": {"visible_text": visible_text},
                },
                "error": None,
            }
        with (run_dir / "run_summary.json").open("w", encoding="utf-8") as file:
            json.dump(summary_data, file)

    def _event_by_source_id(self, semantic_events: dict, source_event_id: str) -> dict:
        for event in semantic_events["events"]:
            if event["source_event_id"] == source_event_id:
                return event
        raise AssertionError(f"missing semantic event for {source_event_id}")

    def _assert_no_visual_leaks(self, serialized: str) -> None:
        self.assertNotIn("raw_step", serialized)
        self.assertNotIn("raw_refs", serialized)
        self.assertNotIn("raw_output_debug", serialized)
        self.assertNotIn('"device"', serialized)
        self.assertNotIn("synthetic screenshot bytes", serialized)
        self.assertNotIn("synthetic_demo_page.jpg", serialized)
        self.assertNotIn("steps/1", serialized)
        self.assertNotIn("\\steps\\1", serialized)


if __name__ == "__main__":
    unittest.main()
