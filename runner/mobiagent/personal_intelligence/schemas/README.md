# Schemas

Minimal JSON Schemas for the Personal Intelligence MVP.

The schemas intentionally stay small:

- `event_schema.json` describes the `pi.semantic.v1` envelope and required derived collections.
- `todo_schema.json` describes todo candidates.
- `profile_schema.json` describes profile fact candidates, not final profile conclusions.
- `relation_schema.json` describes lightweight relation hints only.

All derived records use the same evidence shape: `semantic_event_id`,
`source_event_id`, `field`, and `span`.
