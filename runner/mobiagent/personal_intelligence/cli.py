"""Command-line entry points for the Personal Intelligence extension."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from runner.mobiagent.personal_intelligence.load_workflow_run import load_workflow_run
from runner.mobiagent.personal_intelligence.normalize_events import count_artifacts, normalize_workflow_run


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


def _default_output_path(run_id: str) -> Path:
    return Path("outputs") / "personal_intelligence" / "processed" / f"{run_id}.raw_events.json"


if __name__ == "__main__":
    raise SystemExit(main())
