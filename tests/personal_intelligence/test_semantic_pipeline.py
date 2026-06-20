from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from runner.mobiagent.personal_intelligence.cli import main as cli_main
from runner.mobiagent.personal_intelligence.ingest.extractors import attach_derived
from runner.mobiagent.personal_intelligence.ingest.semantic_events import build_semantic_events
from runner.mobiagent.personal_intelligence.load_workflow_run import load_workflow_run
from runner.mobiagent.personal_intelligence.normalize_events import normalize_workflow_run
from runner.mobiagent.personal_intelligence.service.proactive_service import build_suggestions
from runner.mobiagent.personal_intelligence.service.weekly_report import render_weekly_report
from runner.mobiagent.personal_intelligence.extract.ui_noise_filter import filtered_sentence_spans


class SemanticPipelineTest(unittest.TestCase):
    def test_default_smoke_run_has_no_synthetic_semantics_or_path_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-smoke"
            self._write_smoke_summary(run_dir)

            record = load_workflow_run(run_dir=run_dir)
            raw_events = normalize_workflow_run(record, project_root=project_root)
            semantic_events = build_semantic_events(raw_events)
            attach_derived(semantic_events)
            build_suggestions(semantic_events)

        self.assertEqual(semantic_events["schema_version"], "pi.semantic.v1")
        self.assertEqual(semantic_events["source_run"]["artifact_base"]["type"], "workflow_run_dir")
        self.assertEqual(semantic_events["events"][0]["source_event_id"], raw_events["events"][0]["event_id"])
        self.assertEqual(semantic_events["events"][0]["semantic_event_id"], f"sem:{raw_events['events'][0]['event_id']}")

        for event in semantic_events["events"]:
            self.assertEqual(event["event_type"], "workflow_step")
            self.assertIsNone(event["content"]["text"])
            self.assertEqual(event["content"]["provenance"]["kind"], "empty")
            self.assertFalse(event["content"]["provenance"]["synthetic"])
            self.assertNotIn("derived", event)
            self.assertNotIn("summary", event["content"])
            for artifact in event["artifacts"]:
                self.assertNotIn("path", artifact)

        derived = semantic_events["derived"]
        self.assertEqual(derived["todo_candidates"], [])
        self.assertEqual(derived["time_hints"], [])
        self.assertEqual(derived["entities"], [])
        self.assertEqual(derived["profile_facts"], [])
        self.assertEqual(derived["relations"], [])
        self.assertEqual(derived["suggestions"], [])

        self._assert_no_stage1_leaks(json.dumps(semantic_events, ensure_ascii=False))

    def test_synthetic_fixture_extraction_is_explicit_and_traceable(self) -> None:
        semantic_events = {
            "schema_version": "pi.semantic.v1",
            "source_run": {
                "run_id": "fixture",
                "run_status": "success",
                "workflow_file": None,
                "artifact_base": {"type": None, "path": None},
            },
            "events": [
                {
                    "semantic_event_id": "sem:step:1",
                    "source_event_id": "step:1",
                    "event_type": "workflow_step",
                    "content": {
                        "text": "prepare Android smoke report tomorrow 3pm",
                        "provenance": {
                            "kind": "synthetic_fixture",
                            "synthetic": True,
                        },
                    },
                    "artifacts": [],
                    "metadata": {"step_id": "1", "status": "success"},
                }
            ],
            "derived": {
                "todo_candidates": [],
                "time_hints": [],
                "entities": [],
                "profile_facts": [],
                "relations": [],
                "suggestions": [],
            },
        }

        attach_derived(semantic_events)
        suggestions = build_suggestions(semantic_events)

        derived = semantic_events["derived"]
        todo = derived["todo_candidates"][0]
        time_hint = derived["time_hints"][0]
        entity = derived["entities"][0]

        self.assertEqual(todo["id"], "todo:sem:step:1:1")
        self.assertEqual(todo["semantic_event_id"], "sem:step:1")
        self.assertEqual(todo["source_event_id"], "step:1")
        self.assertEqual(todo["text"], "prepare Android smoke report tomorrow 3pm")
        self.assertEqual(todo["evidence"]["field"], "content.text")
        self.assertEqual(todo["evidence"]["semantic_event_id"], "sem:step:1")
        self.assertEqual(todo["evidence"]["source_event_id"], "step:1")
        self.assertEqual(todo["evidence"]["span"], [0, 41])
        self.assertEqual(time_hint["text"], "tomorrow")
        self.assertEqual(entity["text"], "Android")
        self.assertEqual(suggestions, derived["suggestions"])
        self.assertEqual(suggestions[0]["kind"], "todo_reminder")
        self.assertEqual(
            suggestions[0]["evidence_refs"],
            ["todo:sem:step:1:1", "time:sem:step:1:1", "time:sem:step:1:2"],
        )
        self.assertEqual(suggestions[0]["semantic_event_ids"], ["sem:step:1"])
        self.assertEqual(suggestions[0]["source_event_ids"], ["step:1"])
        self.assertTrue(derived["relations"])

    def test_ui_noise_filter_preserves_original_text_and_derived_spans(self) -> None:
        text = (
            "Search or type web address. "
            "https://10.0.2.2:8000. "
            "Back Home Tabs Menu. "
            "Need to prepare MobiAgent report tomorrow. "
            "I prefer local demos for the project."
        )
        semantic_events = {
            "schema_version": "pi.semantic.v1",
            "source_run": {
                "run_id": "fixture",
                "run_status": "success",
                "workflow_file": None,
                "artifact_base": {"type": None, "path": None},
            },
            "events": [
                {
                    "semantic_event_id": "sem:step:4",
                    "source_event_id": "step:4",
                    "event_type": "workflow_step",
                    "content": {
                        "text": text,
                        "provenance": {
                            "kind": "synthetic_fixture",
                            "synthetic": True,
                        },
                    },
                    "artifacts": [],
                    "metadata": {"step_id": "4", "status": "success"},
                }
            ],
            "derived": {
                "todo_candidates": [],
                "time_hints": [],
                "entities": [],
                "profile_facts": [],
                "relations": [],
                "suggestions": [],
            },
        }

        attach_derived(semantic_events)
        build_suggestions(semantic_events)
        report = render_weekly_report(semantic_events)

        self.assertEqual(semantic_events["events"][0]["content"]["text"], text)
        derived = semantic_events["derived"]
        derived_and_report = json.dumps(derived, ensure_ascii=False) + report
        self.assertNotIn("Search or type web address", derived_and_report)
        self.assertNotIn("10.0.2.2", derived_and_report)
        self.assertNotIn("Back Home Tabs Menu", derived_and_report)

        todo = derived["todo_candidates"][0]
        profile = derived["profile_facts"][0]
        self.assertEqual(todo["text"], "Need to prepare MobiAgent report tomorrow")
        self.assertIn("I prefer local demos for the project", profile["text"])
        self.assertEqual(text[todo["evidence"]["span"][0] : todo["evidence"]["span"][1]], todo["text"])
        self.assertEqual(text[profile["evidence"]["span"][0] : profile["evidence"]["span"][1]], profile["text"])
        self.assertTrue(any(relation["relation_type"] == "has_time" for relation in derived["relations"]))

    def test_ui_noise_filter_preserves_chinese_user_semantic_sentence(self) -> None:
        text = "Back Home Tabs Menu. 记得明天准备 MobiAgent demo，我偏好本地审计流程。"

        spans = filtered_sentence_spans(text)

        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0][0], "记得明天准备 MobiAgent demo，我偏好本地审计流程。")
        self.assertEqual(spans[0][1], text.index("记得"))

    def test_ui_noise_filter_keeps_complete_segment_with_ui_prefix_and_semantics(self) -> None:
        text = (
            "Search or type web address Need to prepare MobiAgent report tomorrow.\n"
            "https://10.0.2.2:8000 I prefer local demos for the project."
        )

        spans = filtered_sentence_spans(text)
        first = "Search or type web address Need to prepare MobiAgent report tomorrow"
        second = "https://10.0.2.2:8000 I prefer local demos for the project"

        self.assertEqual(
            spans,
            [
                (first, 0, len(first)),
                (second, text.index(second), text.index(second) + len(second)),
            ],
        )
        for segment, start, end in spans:
            self.assertEqual(text[start:end], segment)

    def test_run_pipeline_only_writes_requested_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-smoke"
            output_dir = project_root / "semantic_out"
            output_path = output_dir / "semantic_events.json"
            self._write_smoke_summary(run_dir)

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(["run-pipeline", "--run-dir", str(run_dir), "--out", str(output_path)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.is_file())
            self.assertEqual([path for path in output_dir.rglob("*") if path.is_file()], [output_path])

            with output_path.open("r", encoding="utf-8") as file:
                semantic_events = json.load(file)

        self.assertTrue(all(event["content"]["text"] is None for event in semantic_events["events"]))
        self.assertEqual(semantic_events["derived"]["todo_candidates"], [])
        self.assertEqual(semantic_events["derived"]["time_hints"], [])
        self.assertEqual(semantic_events["derived"]["entities"], [])
        self.assertEqual(semantic_events["derived"]["profile_facts"], [])
        self.assertEqual(semantic_events["derived"]["relations"], [])
        self.assertEqual(semantic_events["derived"]["suggestions"], [])
        self._assert_no_stage1_leaks(json.dumps(semantic_events, ensure_ascii=False))

    def test_synthetic_fixture_mode_generates_debug_report_without_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-smoke"
            output_dir = project_root / "semantic_out"
            output_path = output_dir / "semantic_events.json"
            report_path = output_dir / "weekly_report.md"
            report_copy_path = output_dir / "weekly_report_from_json.md"
            fixture_path = project_root / "fixtures" / "synthetic_text.json"
            self._write_smoke_summary(run_dir)
            self._write_text_fixture(
                fixture_path,
                "prepare Android smoke report tomorrow 3pm. "
                "I prefer WeChat for MobiAgent project updates.",
            )

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(
                    [
                        "run-pipeline",
                        "--run-dir",
                        str(run_dir),
                        "--out",
                        str(output_path),
                        "--text-provenance",
                        "synthetic_fixture",
                        "--text-fixture",
                        str(fixture_path),
                        "--report-out",
                        str(report_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertTrue(output_path.is_file())
            self.assertTrue(report_path.is_file())
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(["report", "--in", str(output_path), "--out", str(report_copy_path)])
            self.assertEqual(exit_code, 0)
            self.assertTrue(report_copy_path.is_file())
            with output_path.open("r", encoding="utf-8") as file:
                semantic_events = json.load(file)
            report = report_path.read_text(encoding="utf-8")
            report_copy = report_copy_path.read_text(encoding="utf-8")

        event = semantic_events["events"][0]
        self.assertEqual(event["content"]["provenance"]["kind"], "synthetic_fixture")
        self.assertTrue(event["content"]["provenance"]["synthetic"])
        derived = semantic_events["derived"]
        self.assertTrue(derived["todo_candidates"])
        self.assertTrue(derived["time_hints"])
        self.assertTrue(derived["entities"])
        self.assertTrue(derived["profile_facts"])
        self.assertTrue(derived["relations"])
        self.assertTrue(derived["suggestions"])
        self.assertIn("Personal Intelligence Local Baseline/Debug Report", report)
        self.assertIn(
            "This report is generated from local baseline extraction for contract validation and demo review. "
            "It is not a final user-facing intelligence report.",
            report,
        )
        for section in ("Highlights", "Possible Tasks", "Time References", "Context Notes", "Evidence"):
            self.assertIn(f"## {section}", report)
        self.assertNotIn("Profile Fact Candidates", report)
        self.assertNotIn("Relation Hints", report)
        self.assertNotIn("Proactive Suggestions", report)
        self.assertNotIn("relation:", report)
        self.assertNotIn("from_id", report)
        self.assertNotIn("to_id", report)
        self.assertIn("Evidence: sem:step:1 / step:1 span", report)
        self.assertEqual(report, report_copy)

        serialized = json.dumps(semantic_events, ensure_ascii=False) + report
        self._assert_no_stage1_leaks(serialized)

    def test_cli_synthetic_texts_fixture_maps_by_source_event_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-five-step"
            output_path = project_root / "semantic_out" / "semantic_events.json"
            fixture_path = project_root / "fixtures" / "synthetic_texts.json"
            meeting_text = "prepare research report tomorrow 3pm"
            preference_text = "I prefer local lightweight auditable MobiAgent demos"
            self._write_five_step_summary(run_dir)
            self._write_texts_fixture(
                fixture_path,
                {
                    "step:2": meeting_text,
                    "step:5": preference_text,
                },
            )

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(
                    [
                        "run-pipeline",
                        "--run-dir",
                        str(run_dir),
                        "--out",
                        str(output_path),
                        "--text-provenance",
                        "synthetic_fixture",
                        "--text-fixture",
                        str(fixture_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            with output_path.open("r", encoding="utf-8") as file:
                semantic_events = json.load(file)

        step2 = self._event_by_source_id(semantic_events, "step:2")
        step5 = self._event_by_source_id(semantic_events, "step:5")
        self.assertEqual(step2["content"]["text"], meeting_text)
        self.assertEqual(step5["content"]["text"], preference_text)
        self.assertEqual(step2["content"]["provenance"]["kind"], "synthetic_fixture")
        self.assertTrue(step2["content"]["provenance"]["synthetic"])
        derived = semantic_events["derived"]
        self.assertTrue(derived["todo_candidates"] or derived["time_hints"] or derived["entities"])

    def test_cli_synthetic_fixture_warns_when_no_keys_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-five-step"
            output_path = project_root / "semantic_out" / "semantic_events.json"
            fixture_path = project_root / "fixtures" / "synthetic_texts.json"
            self._write_five_step_summary(run_dir)
            self._write_texts_fixture(
                fixture_path,
                {"evt_20260617-173337-android-smoke-workflow_000002": "prepare research report tomorrow"},
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = cli_main(
                    [
                        "run-pipeline",
                        "--run-dir",
                        str(run_dir),
                        "--out",
                        str(output_path),
                        "--text-provenance",
                        "synthetic_fixture",
                        "--text-fixture",
                        str(fixture_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            with output_path.open("r", encoding="utf-8") as file:
                semantic_events = json.load(file)

        output = stdout.getvalue()
        self.assertIn("warning: text fixture did not match any semantic source_event_id", output)
        self.assertIn("available source_event_id: step:1, step:2, step:3, step:4, step:5", output)
        self.assertIn("evt_20260617-173337-android-smoke-workflow_000002", output)
        self.assertTrue(all(event["content"]["text"] is None for event in semantic_events["events"]))
        self.assertEqual(semantic_events["derived"]["todo_candidates"], [])
        self.assertEqual(semantic_events["derived"]["time_hints"], [])
        self.assertEqual(semantic_events["derived"]["entities"], [])

    def test_local_private_demo_mode_only_uses_explicit_text_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-smoke"
            output_dir = project_root / "semantic_out"
            empty_output_path = output_dir / "local_private_empty.json"
            output_path = output_dir / "local_private_events.json"
            fixture_path = project_root / "fixtures" / "local_private_text.json"
            self._write_smoke_summary(run_dir)

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(
                    [
                        "run-pipeline",
                        "--run-dir",
                        str(run_dir),
                        "--out",
                        str(empty_output_path),
                        "--text-provenance",
                        "local_private",
                    ]
                )
            self.assertEqual(exit_code, 0)
            with empty_output_path.open("r", encoding="utf-8") as file:
                empty_semantic_events = json.load(file)

            self._write_text_fixture(
                fixture_path,
                "Need to follow up MobiAgent project next week. I usually use WeChat for project notes.",
            )
            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(
                    [
                        "run-pipeline",
                        "--run-dir",
                        str(run_dir),
                        "--out",
                        str(output_path),
                        "--text-provenance",
                        "local_private",
                        "--text-fixture",
                        str(fixture_path),
                    ]
                )
            self.assertEqual(exit_code, 0)
            with output_path.open("r", encoding="utf-8") as file:
                semantic_events = json.load(file)

        self.assertTrue(all(event["content"]["text"] is None for event in empty_semantic_events["events"]))
        self.assertEqual(empty_semantic_events["derived"]["todo_candidates"], [])
        self.assertEqual(empty_semantic_events["derived"]["profile_facts"], [])

        event = semantic_events["events"][0]
        self.assertEqual(event["content"]["provenance"]["kind"], "local_private")
        self.assertFalse(event["content"]["provenance"]["synthetic"])
        derived = semantic_events["derived"]
        self.assertTrue(derived["todo_candidates"])
        self.assertTrue(derived["profile_facts"])
        self.assertTrue(derived["relations"])

    def test_demo_local_text_alias_uses_fixture_with_local_private_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir) / "project"
            run_dir = project_root / "outputs" / "personal_intelligence" / "raw_runs" / "unit-five-step"
            output_path = project_root / "semantic_out" / "local_private_events.json"
            fixture_path = project_root / "fixtures" / "local_private_texts.json"
            text = "I prefer local lightweight auditable MobiAgent demos"
            self._write_five_step_summary(run_dir)
            self._write_texts_fixture(fixture_path, {"step:5": text})

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = cli_main(
                    [
                        "run-pipeline",
                        "--run-dir",
                        str(run_dir),
                        "--out",
                        str(output_path),
                        "--demo-local-text",
                        "--text-fixture",
                        str(fixture_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            with output_path.open("r", encoding="utf-8") as file:
                semantic_events = json.load(file)

        event = self._event_by_source_id(semantic_events, "step:5")
        self.assertEqual(event["content"]["text"], text)
        self.assertEqual(event["content"]["provenance"]["kind"], "local_private")
        self.assertFalse(event["content"]["provenance"]["synthetic"])

    def _write_smoke_summary(self, run_dir: Path) -> None:
        screenshot_path = run_dir / "steps" / "2" / "home_before_swipe.jpg"
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.write_bytes(b"fake screenshot bytes")
        run_dir.mkdir(parents=True, exist_ok=True)

        summary = {
            "workflow_file": "runner/mobiagent/personal_intelligence/examples/workflows/android_smoke_workflow.json",
            "run_dir": str(run_dir),
            "context": {},
            "steps": {
                "1": {
                    "step_id": "1",
                    "status": "success",
                    "started_at": 1.0,
                    "finished_at": 1.5,
                    "duration_sec": 0.5,
                    "output": {"key": "HOME", "device": "Android"},
                    "error": None,
                },
                "2": {
                    "step_id": "2",
                    "status": "success",
                    "started_at": 2.0,
                    "finished_at": 3.0,
                    "duration_sec": 1.0,
                    "output": {"image_path": str(screenshot_path), "device": "Android"},
                    "error": None,
                },
            },
            "status": "success",
        }
        with (run_dir / "run_summary.json").open("w", encoding="utf-8") as file:
            json.dump(summary, file)

    def _write_five_step_summary(self, run_dir: Path) -> None:
        run_dir.mkdir(parents=True, exist_ok=True)
        steps = {}
        for index in range(1, 6):
            steps[str(index)] = {
                "step_id": index,
                "status": "success",
                "started_at": float(index),
                "finished_at": float(index) + 0.5,
                "duration_sec": 0.5,
                "output": {"key": "HOME"} if index == 1 else {"status": "ok"},
                "error": None,
            }

        summary = {
            "workflow_file": "runner/mobiagent/personal_intelligence/examples/workflows/android_smoke_workflow.json",
            "run_dir": str(run_dir),
            "context": {},
            "steps": steps,
            "status": "success",
        }
        with (run_dir / "run_summary.json").open("w", encoding="utf-8") as file:
            json.dump(summary, file)

    def _write_text_fixture(self, fixture_path: Path, text: str) -> None:
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        fixture = {
            "events": [
                {
                    "source_event_id": "step:1",
                    "content": {
                        "text": text,
                    },
                }
            ]
        }
        with fixture_path.open("w", encoding="utf-8") as file:
            json.dump(fixture, file)

    def _write_texts_fixture(self, fixture_path: Path, texts: dict[str, str]) -> None:
        fixture_path.parent.mkdir(parents=True, exist_ok=True)
        with fixture_path.open("w", encoding="utf-8") as file:
            json.dump({"texts": texts}, file, ensure_ascii=False)

    def _event_by_source_id(self, semantic_events: dict, source_event_id: str) -> dict:
        for event in semantic_events["events"]:
            if event["source_event_id"] == source_event_id:
                return event
        raise AssertionError(f"missing semantic event for {source_event_id}")

    def _assert_no_stage1_leaks(self, serialized: str) -> None:
        self.assertNotIn("raw_step", serialized)
        self.assertNotIn("raw_refs", serialized)
        self.assertNotIn('"device"', serialized)
        self.assertNotIn("fake screenshot bytes", serialized)
        self.assertNotIn("home_before_swipe.jpg", serialized)
        self.assertNotIn("steps/2", serialized)
        self.assertNotIn("\\steps\\2", serialized)


if __name__ == "__main__":
    unittest.main()
