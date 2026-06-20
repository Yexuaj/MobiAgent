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

Stage 3A adds a conservative UI noise filter before derived extraction. The
filter only affects todo/time/entity/profile extraction inputs and report
content; it does not rewrite `semantic_events[*].content.text`. Evidence spans
still refer to the original `content.text`. The weekly report is now a local
baseline/debug skeleton with `Highlights`, `Possible Tasks`, `Time References`,
`Context Notes`, and `Evidence` sections instead of a full relation graph dump.

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

## Stage 2 Visual Text Provider

Visual text remains disabled by default. To opt in, pass
`--enable-visual-text --visual-text-provider workflow_vlm_qa_output`.

`workflow_vlm_qa_output` is the Stage 2 e2e-validated provider. It reads text
already returned by a workflow `vlm_qa` step, preferring
`output.structured_output.visible_text` and falling back to summary/response
fields. The provider maps that text back to the screenshot event that supplied
the image and records provenance as `workflow_vlm_qa` with
`provider=workflow_vlm_qa_output`.

This provider requires an OpenAI-compatible vision service wired through the
workflow `vlm_qa` tool. The example workflow under `examples/workflows/` uses a
synthetic demo page only; it does not contain real accounts, chats, or private
data.
