# Personal Intelligence

Personal Intelligence is a low-coupled MobiAgent extension for ingesting
workflow run artifacts, extracting user-relevant signals, storing structured
memory, and generating personal services such as reports or task augmentation.

This Stage 1 pipeline focuses on the safe data contract:

- `none` (default): safe mode. It does not read real text, so semantic event
  text stays `null` and derived hints stay empty for smoke runs.
- `synthetic_fixture`: test/demo fixture mode. It requires `--text-fixture`,
  marks text as synthetic, and never loads built-in demo data.
- `local_private`: local demo mode. It requires explicit opt-in and only uses
  short allowlisted text supplied through a fixture/demo JSON. It does not scan
  raw workflow output, metadata, artifact paths, screenshots, or raw steps.

The report command is a baseline/debug renderer for contract validation and
leak checks. It is not a final user-facing weekly report.

Examples:

```bash
python -m runner.mobiagent.personal_intelligence.cli run-pipeline \
  --run-dir outputs/personal_intelligence/raw_runs/<run_id> \
  --out outputs/personal_intelligence/processed/<run_id>.semantic_events.json
```

```bash
python -m runner.mobiagent.personal_intelligence.cli run-pipeline \
  --run-dir outputs/personal_intelligence/raw_runs/<run_id> \
  --out outputs/personal_intelligence/processed/<run_id>.semantic_events.json \
  --text-provenance local_private \
  --text-fixture local_demo_text.json \
  --report-out
```

Recommended `--text-fixture` JSON:

```json
{
  "texts": {
    "step:2": "prepare Android smoke report tomorrow 3pm",
    "step:5": "I prefer local, lightweight, auditable Personal Intelligence demos"
  }
}
```

Fixture keys must match the semantic event `source_event_id` generated from the
workflow summary, usually `step:<step_key>` such as `step:2`. `sem:step:2` is
also accepted. The loader still accepts the legacy explicit event-record forms
used by tests:

```json
{"events": [{"source_event_id": "step:2", "content": {"text": "..."}}]}
```

```json
[{"event_id": "step:2", "text": "..."}]
```

When `--report-out` is passed without a path, the debug report is written to
`outputs/personal_intelligence/generated/<run_id>.weekly_report.md`.
