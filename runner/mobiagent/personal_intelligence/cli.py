"""Command-line entry points for the Personal Intelligence extension."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from runner.mobiagent.personal_intelligence.load_workflow_run import load_workflow_run
from runner.mobiagent.personal_intelligence.normalize_events import count_artifacts, normalize_workflow_run
from runner.mobiagent.personal_intelligence.extract.extract_text import load_text_fixture
from runner.mobiagent.personal_intelligence.ingest.extractors import attach_derived
from runner.mobiagent.personal_intelligence.ingest.load_workflow_run import load_workflow_run as load_pipeline_run
from runner.mobiagent.personal_intelligence.ingest.semantic_events import (
    TEXT_PROVENANCE_LOCAL_PRIVATE,
    TEXT_PROVENANCE_NONE,
    TEXT_PROVENANCE_SYNTHETIC,
    build_semantic_events,
)
from runner.mobiagent.personal_intelligence.ingest.visual_text_adapter import (
    PROVIDER_WORKFLOW_VLM_QA_OUTPUT,
    VISUAL_TEXT_PROVIDERS,
    build_visual_text_inputs,
)
from runner.mobiagent.personal_intelligence.service.proactive_service import build_suggestions
from runner.mobiagent.personal_intelligence.service.weekly_report import (
    load_semantic_events,
    write_weekly_report,
)

DEFAULT_REPORT_SENTINEL = "__default_report_path__"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="MobiAgent Personal Intelligence tools")
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_run = subparsers.add_parser(
        "import-run",
        help="Import a workflow run directory as Personal Intelligence raw events JSON.",
    )
    import_run.add_argument("--run-dir", help="Workflow run directory containing run_summary.json.")
    import_run.add_argument("--summary", help="Explicit run_summary.json path.")
    import_run.add_argument("--out", help="Output raw_events JSON path.")
    import_run.add_argument(
        "--include-raw-step",
        action="store_true",
        help="Include the full raw step dictionary in each event for debugging.",
    )
    import_run.set_defaults(func=_import_run)

    run_pipeline = subparsers.add_parser(
        "run-pipeline",
        help="Run the minimal semantic pipeline over a workflow run directory.",
    )
    run_pipeline.add_argument("--run-dir", required=True, help="Workflow run directory containing run_summary.json.")
    run_pipeline.add_argument("--out", required=True, help="Output semantic_events JSON path.")
    run_pipeline.add_argument(
        "--text-provenance",
        choices=[TEXT_PROVENANCE_NONE, TEXT_PROVENANCE_LOCAL_PRIVATE, TEXT_PROVENANCE_SYNTHETIC],
        default=TEXT_PROVENANCE_NONE,
        help="Explicit text mode. Default keeps semantic text empty.",
    )
    run_pipeline.add_argument(
        "--text-fixture",
        help="Explicit short-text fixture/demo JSON. Required for synthetic_fixture mode.",
    )
    run_pipeline.add_argument(
        "--demo-local-text",
        action="store_true",
        help="Alias for --text-provenance local_private for local demos.",
    )
    run_pipeline.add_argument(
        "--report-out",
        nargs="?",
        const=DEFAULT_REPORT_SENTINEL,
        help="Optionally write weekly_report.md. Without a value, uses outputs/personal_intelligence/generated/.",
    )
    run_pipeline.add_argument(
        "--enable-visual-text",
        action="store_true",
        help="Enable an explicit visual text provider. Default leaves visual text disabled.",
    )
    run_pipeline.add_argument(
        "--visual-text-provider",
        choices=list(VISUAL_TEXT_PROVIDERS),
        default=PROVIDER_WORKFLOW_VLM_QA_OUTPUT,
        help="Visual text provider to use when --enable-visual-text is set.",
    )
    run_pipeline.add_argument(
        "--visual-text-max-events",
        type=int,
        help="Optional maximum number of events populated by visual text.",
    )
    run_pipeline.add_argument(
        "--visual-text-max-chars",
        type=int,
        help="Optional maximum characters kept per visual text event.",
    )
    run_pipeline.set_defaults(func=_run_pipeline)

    report = subparsers.add_parser(
        "report",
        help="Render weekly_report.md from an existing semantic_events JSON file.",
    )
    report.add_argument("--in", dest="input", required=True, help="Input semantic_events JSON path.")
    report.add_argument("--out", required=True, help="Output weekly_report.md path.")
    report.set_defaults(func=_report)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args, parser)


def _import_run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if not args.run_dir and not args.summary:
        parser.error("import-run requires --run-dir, --summary, or both.")

    record = load_workflow_run(run_dir=args.run_dir, summary_path=args.summary)
    raw_events = normalize_workflow_run(record, include_raw_step=args.include_raw_step)
    output_path = Path(args.out) if args.out else _default_output_path(raw_events["run_id"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(raw_events, file, ensure_ascii=False, indent=2)
        file.write("\n")

    event_count = len(raw_events.get("events", []))
    artifact_count = count_artifacts(raw_events)
    print(f"output: {output_path}")
    print(f"events: {event_count}")
    print(f"artifacts: {artifact_count}")
    return 0


def _run_pipeline(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    text_provenance = _resolve_text_provenance(args, parser)
    if args.text_fixture and text_provenance == TEXT_PROVENANCE_NONE:
        parser.error("--text-fixture requires --text-provenance local_private or synthetic_fixture.")
    if text_provenance == TEXT_PROVENANCE_SYNTHETIC and not args.text_fixture:
        parser.error("--text-provenance synthetic_fixture requires --text-fixture.")

    text_inputs = load_text_fixture(args.text_fixture) if args.text_fixture else {}
    text_provenance_inputs: dict[str, dict] = {}
    record = load_pipeline_run(run_dir=args.run_dir)
    raw_events = normalize_workflow_run(record)
    if args.text_fixture:
        _warn_if_text_fixture_unmatched(text_inputs, raw_events)
    if args.enable_visual_text:
        visual_inputs = build_visual_text_inputs(
            record,
            raw_events,
            provider=args.visual_text_provider,
            max_events=args.visual_text_max_events,
            max_chars=args.visual_text_max_chars,
        )
        text_inputs.update(visual_inputs.text_inputs)
        text_provenance_inputs.update(visual_inputs.text_provenance_inputs)

    semantic_events = build_semantic_events(
        raw_events,
        text_provenance=text_provenance,
        text_inputs=text_inputs,
        text_provenance_inputs=text_provenance_inputs,
    )
    attach_derived(semantic_events)
    suggestions = build_suggestions(semantic_events)

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as file:
        json.dump(semantic_events, file, ensure_ascii=False, indent=2)
        file.write("\n")

    derived = semantic_events.get("derived", {})
    report_path = _maybe_write_report(args.report_out, semantic_events)
    print(f"output: {output_path}")
    print(f"events: {len(semantic_events.get('events', []))}")
    print(f"todo_candidates: {len(derived.get('todo_candidates', []))}")
    print(f"time_hints: {len(derived.get('time_hints', []))}")
    print(f"entities: {len(derived.get('entities', []))}")
    print(f"profile_facts: {len(derived.get('profile_facts', []))}")
    print(f"relations: {len(derived.get('relations', []))}")
    print(f"suggestions: {len(suggestions)}")
    if report_path is not None:
        print(f"weekly_report: {report_path}")
    return 0


def _report(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    semantic_events = load_semantic_events(args.input)
    output_path = write_weekly_report(semantic_events, args.out)
    print(f"weekly_report: {output_path}")
    return 0


def _default_output_path(run_id: str) -> Path:
    return Path("outputs") / "personal_intelligence" / "processed" / f"{run_id}.raw_events.json"


def _default_report_path(semantic_events: dict) -> Path:
    source_run = semantic_events.get("source_run") if isinstance(semantic_events.get("source_run"), dict) else {}
    run_id = source_run.get("run_id") or "semantic_events"
    return Path("outputs") / "personal_intelligence" / "generated" / f"{run_id}.weekly_report.md"


def _resolve_text_provenance(args: argparse.Namespace, parser: argparse.ArgumentParser) -> str:
    text_provenance = args.text_provenance
    if args.demo_local_text:
        if text_provenance not in (TEXT_PROVENANCE_NONE, TEXT_PROVENANCE_LOCAL_PRIVATE):
            parser.error("--demo-local-text cannot be combined with --text-provenance synthetic_fixture.")
        text_provenance = TEXT_PROVENANCE_LOCAL_PRIVATE
    return text_provenance


def _warn_if_text_fixture_unmatched(text_inputs: dict[str, str], raw_events: dict) -> None:
    available_source_ids = [
        str(event.get("event_id"))
        for event in raw_events.get("events", [])
        if isinstance(event, dict) and event.get("event_id") is not None
    ]
    allowed_ids = set(available_source_ids)
    allowed_ids.update(f"sem:{source_id}" for source_id in available_source_ids)
    if any(event_id in allowed_ids for event_id in text_inputs):
        return

    available = ", ".join(available_source_ids) if available_source_ids else "(none)"
    provided = ", ".join(sorted(text_inputs)) if text_inputs else "(none)"
    print(
        "warning: text fixture did not match any semantic source_event_id; "
        f"available source_event_id: {available}; fixture keys: {provided}"
    )


def _maybe_write_report(report_arg: str | None, semantic_events: dict) -> Path | None:
    if report_arg is None:
        return None
    report_path = _default_report_path(semantic_events) if report_arg == DEFAULT_REPORT_SENTINEL else Path(report_arg)
    return write_weekly_report(semantic_events, report_path)


if __name__ == "__main__":
    raise SystemExit(main())
