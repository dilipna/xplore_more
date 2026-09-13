# Event contracts

JSON Schemas here are the **single source of truth** for events that cross the Go edge (`apps/edge-go`) and the Python data plane (`packages/xm_core`, `apps/indexer`).

- `events/*.schema.json`: envelope and per-type payloads (JSON Schema 2020-12)
- `fixtures/*.json`: canonical example messages. **Both** the Go and the Python test suites validate these fixtures and round-trip them through their native types. A schema change that breaks either side fails CI.

## Rules

1. **Additive changes only** within a major version (new optional fields). Removing or retyping a field requires a new `type` suffix (`.v2`) and a period where consumers accept both.
2. **Pointers, not bodies.** Full text lives in object storage (`text_uri`), so message size stays around 1 KB.
3. **Deploy consumers first.** Consumers decode strictly (unknown fields fail), so an additive field ships in the ingestor and indexer before any producer emits it. `fixtures/legacy/` holds pre-change messages that must keep validating.
4. **Document kinds** (`doc_kind`, added 2026-09-13). `article` is a fetched page. `discussion` is a post or comment read from a platform API (`discussion.v1.schema.json`): its text travels in `feed_summary`, the ingestor never fetches its HTML, and it carries `platform`, `thread_url`, `parent_url`, a salted `author_hash` (no usernames cross the edge) and as-of `engagement`. Discussions never join news stories; they feed problem clustering.
5. **Idempotency key** = `sha256("{type}|{subject}|{discriminator}")`:
   - `article.discovered`: discriminator is empty.
   - `article.extracted`: discriminator is `content_hash`. A changed article re-extracts; an unchanged redelivery is a no-op.
