# Tutorial Module Design

Date: 2026-03-14
Status: Revised after external review

## Summary

Add a new Galaxy tutorial module to KaTrain Web, parallel to existing modules such as Play, Live, and Tsumego.

The module serves structured voice-guided Go lessons built from externally parsed book data, but the public product must not expose book titles, authors, translators, or near-verbatim source text. Public lessons are organized as:

`Tutorial -> Category -> Topic -> Example -> Step`

Phase 1 uses existing page screenshots as the visual layer. A later phase may replace screenshot-based steps with SGF-backed interactive board views without changing the public hierarchy.

## Goals

1. Ship a first-class Web tutorial module inside Galaxy, with both backend and frontend support.
2. Build a safe content pipeline from parsed `book.json` inputs to public lesson artifacts.
3. Generate narrated audio lessons offline using CosyVoice as the TTS subsystem.
4. Keep the online product read-only with respect to lesson generation: all public lesson content is prebuilt, reviewed, and published offline.
5. Preserve a migration path from screenshot steps to SGF-driven board visualization.

## Non-Goals

1. No desktop/Kivy tutorial UI in phase 1.
2. No online lesson authoring CMS in phase 1.
3. No real-time TTS generation in the public app.
4. No source-book attribution in the public UI or public APIs.
5. No fully automated publish path without human review.

## Product Requirements

### User-visible structure

The public module is structured as:

- `Tutorial`: the top-level Galaxy module entry.
- `Category`: broad learning stages such as `beginner`, `opening`, `middle-game`, `endgame`.
- `Topic`: a public knowledge unit, not a raw book chapter.
- `Example`: one teaching sequence under a topic.
- `Step`: the smallest playback unit, containing narration, image/board payload, and audio.

### Content policy

Public content must:

1. Avoid book names, author names, translator names, raw chapter headings, and source-specific provenance.
2. Rewrite source text into concise spoken instruction suitable for audio playback.
3. Avoid near-verbatim reproduction of source passages.
4. Remove OCR noise, redundant phrasing, special symbols, and page furniture.
5. Be auditable before publication.
6. Sanitize source screenshots before publication by cropping away non-board page furniture where possible.

### Known legal risk

Phase 1 still uses screenshot-derived visual material. Even without exposing book identity, those images may still carry copyright risk because they are derived from protected page content.

This is an explicitly accepted phase-1 product risk, with the following mitigation:

1. Do not expose book identity in the product or public APIs.
2. Crop page furniture, margins, headers, footers, and other source-identifying visual residue wherever possible.
3. Treat screenshot visuals as a temporary rendering layer to be replaced by SGF-backed board views in a later phase.
4. Keep the screenshot-processing stage isolated so it can be swapped out without redesigning the public lesson model.

### First release scope

Phase 1 includes:

1. Category browsing
2. Topic browsing within a category
3. Example playback page with step navigation
4. Screenshot-based visuals
5. Offline-generated audio
6. User progress tracking

## Source Input and Editorial Boundary

The initial content source is parsed book output such as:

- `output/book.json`
- `output/review.json`
- extracted page screenshots

Example source path used during design:

- `/Users/fan/Repositories/go-topic-collections/books/布局/曹薰铉布局技巧_上册_曹薰铉_1997/output/book.json`

That source shows a useful internal hierarchy:

- `chapters`
- `sections`
- `pages`
- `elements`

This hierarchy is sufficient for an offline builder to derive lesson fragments, but it must remain private. It is not the public product model.

## Recommended Architecture

Use a three-layer architecture:

### 1. Private source layer

Contains raw parsed materials and source metadata:

- `book.json`
- `review.json`
- page screenshots
- source file paths
- raw text fragments
- figure labels
- page references

This layer is never exposed to public APIs or the public UI.

### 2. Editorial build layer

Offline pipeline that transforms source content into public tutorial artifacts:

1. Ingest parsed source files.
2. Extract source fragments.
3. Map fragments into public lesson categories.
4. Merge similar source sections into public `topic` units.
5. Split each topic into one or more `example` sequences.
6. Split each example into short `step` units suitable for narration.
7. Rewrite narration into spoken teaching copy.
8. Call CosyVoice to generate step-level audio.
9. Write draft outputs for manual review.
10. Publish reviewed content into a public lesson package.

### 3. Public app layer

KaTrain Web reads published lesson packages and exposes:

- tutorial browsing APIs
- example detail APIs
- progress APIs
- Galaxy tutorial pages

This layer must not contain raw source metadata.

## Data Model

### Private editorial objects

These exist only in the offline review workflow.

#### `SourceFragment`

- `source_id`
- `source_path`
- `page`
- `image_ref`
- `raw_text`
- `figure_label`
- `bbox`

#### `DraftTopic`

- `topic_slug`
- `stable_id`
- `category`
- `working_title`
- `teaching_goal`
- `source_refs[]`

#### `DraftExample`

- `example_id`
- `stable_id`
- `topic_slug`
- `draft_title`
- `source_refs[]`
- `steps[]`
- `total_duration_sec?`

#### `DraftStep`

- `step_id`
- `narration_draft`
- `narration_final`
- `image_ref`
- `board_mode`
- `board_payload`
- `audio_ref`
- `audio_duration_ms?`
- `rewrite_similarity_score?`

`board_mode` is expected to be `image` in phase 1 and may later become `sgf`.

#### `ReviewRecord`

- `status`
- `reviewer`
- `reviewed_at`
- `notes`
- `rejection_reason`

Recommended minimum workflow:

- `draft`
- `approved`
- `published`

### Public lesson objects

These are safe to expose through the public app.

#### `Category`

- `id`
- `slug`
- `title`
- `summary`
- `order`
- `topic_count`
- `cover_asset`

#### `Topic`

- `id`
- `category_id`
- `slug`
- `title`
- `summary`
- `tags[]?`
- `difficulty?`
- `estimated_minutes?`

#### `Example`

- `id`
- `topic_id`
- `title`
- `summary`
- `order`
- `total_duration_sec`
- `step_count`

#### `Step`

- `id`
- `example_id`
- `order`
- `narration`
- `image_asset`
- `audio_asset`
- `audio_duration_ms`
- `board_mode`
- `board_payload`

Phase-1 rendering contract:

1. If `board_mode=image`, the frontend renders `image_asset` and `board_payload` must be `null`.
2. If `board_mode=sgf`, the frontend renders from `board_payload` and `image_asset` becomes optional fallback media.

#### `UserProgress`

- `user_id`
- `topic_id`
- `example_id`
- `last_step_id`
- `completed`
- `last_played_at`

`UserProgress` is dynamic online data and is not part of the published content package.

## Published Package Format

Recommended published package layout:

```text
data/tutorials_published/
  manifest.json
  categories/
    opening.json
    middle-game.json
  topics/
    opening/
      balance-corner-and-influence.json
  examples/
    ex_opening_001.json
    ex_opening_002.json
  assets/
    images/
      ex_opening_001_step_01.png
    audio/
      ex_opening_001_step_01.mp3
```

Rules for published packages:

1. Do not include source identity fields such as book title, author, translator, or source path.
2. Do not include raw extracted source text.
3. Include only final rewritten narration.
4. Include only `published` content.
5. Keep `board_mode` explicit so the app can support both screenshot and SGF steps.

## Code Placement

### Offline builder

Recommended phase-1 package:

```text
katrain/tutorial_builder/
  pipeline.py
  ingest.py
  build.py
  rewrite.py
  tts.py
  publish.py
  ids.py
```

Reasoning:

- The builder belongs with the product because the publish format and app behavior will evolve together.
- It should not live inside the online runtime package.
- It should not depend on the source-book repository for long-term maintainability.
- Phase 1 should start with a flatter structure and only split into subpackages after the first end-to-end path is proven.

### Online backend

Recommended placement:

```text
katrain/web/tutorials/
  loader.py
  service.py
  progress.py
katrain/web/api/v1/endpoints/tutorials.py
```

This follows the existing `api/v1` endpoint pattern already used by modules such as Tsumego, Kifu, and Live.

### Online frontend

Recommended placement:

```text
katrain/web/ui/src/galaxy/api/tutorials.ts
katrain/web/ui/src/galaxy/types/tutorials.ts
katrain/web/ui/src/galaxy/pages/tutorials/
katrain/web/ui/src/galaxy/components/tutorials/
```

Also update:

- `katrain/web/ui/src/GalaxyApp.tsx`
- `katrain/web/ui/src/galaxy/components/layout/GalaxySidebar.tsx`
- dashboard module cards if the tutorial module should appear there as well

## Backend API Shape

Recommended phase-1 endpoints:

- `GET /api/v1/tutorials/categories`
- `GET /api/v1/tutorials/categories/{slug}/topics`
- `GET /api/v1/tutorials/topics/{topic_id}`
- `GET /api/v1/tutorials/examples/{example_id}`
- `GET /api/v1/tutorials/examples/{example_id}/assets/{asset_id}` if asset indirection is needed
- `GET /api/v1/tutorials/progress`
- `POST /api/v1/tutorials/progress/{example_id}`

Notes:

1. Content endpoints should read from the published package index.
2. Progress endpoints may store per-user state in the existing database stack.
3. Public content payloads should stay stable even if the source pipeline changes.

## ID Stability

Published IDs must be stable across rebuilds. Otherwise stored `UserProgress` becomes invalid.

Phase-1 rule:

1. `topic_id` and `example_id` are generated deterministically from normalized editorial identity, not from build order.
2. The builder keeps a persistent ID mapping record for any cases where deterministic derivation would otherwise change after editorial renames.
3. Rebuilds must preserve published IDs unless an editor explicitly performs a breaking content migration.

Recommended implementation options:

1. Deterministic hash from canonicalized editorial keys
2. A checked-in ID map file maintained by the builder

Either approach is acceptable, but planning must pick one and test rebuild stability explicitly.

## Frontend UX Shape

Recommended phase-1 page flow:

1. Tutorial landing page: category cards
2. Topic listing page: topics under the selected category
3. Topic detail page: topic summary plus ordered examples
4. Example playback page:
   - screenshot or board panel
   - narration text
   - audio playback
   - step navigation
   - completion/progress state

The example playback page is the core learning surface and should treat `Step` as the primary playback unit.

## TTS Integration

Use CosyVoice as a replaceable offline TTS subsystem.

Why this is acceptable:

- The official repository publicly documents service deployment under `runtime/python/fastapi` and `grpc`, plus text normalization and streaming support.
- Those capabilities are sufficient for batch or service-based lesson audio generation.

Why this is not enough by itself:

- CosyVoice does not solve topic deduplication.
- CosyVoice does not solve copyright-safe rewriting.
- CosyVoice does not solve editorial review or publish rules.

Therefore:

1. The builder owns rewrite and publishing policy.
2. CosyVoice only converts approved or draft narration text into audio assets.

Phase-1 TTS assumptions:

1. Use the HTTP FastAPI deployment path first, not gRPC, to minimize integration cost.
2. Use a fixed preset voice in phase 1; no voice cloning.
3. Generate audio offline in batch mode.
4. Validate a short pronunciation whitelist for Go terms such as `三三`, `天元`, and `小目` before scaling content generation.

Source:

- https://github.com/FunAudioLLM/CosyVoice

## Narration Rewrite Mechanism

The rewrite stage is an explicit subsystem, not an unspecified editorial note.

Phase-1 mechanism:

1. Use an offline LLM-assisted rewrite step with a fixed prompt template and structured output schema.
2. Input:
   - source fragment text
   - category/topic context
   - desired spoken style constraints
3. Output schema:
   - `spoken_title?`
   - `narration_final`
   - `key_terms[]`
   - `safety_notes?`
4. Rewrite constraints:
   - concise spoken Chinese
   - no book names or source provenance
   - no long verbatim spans from source
   - remove OCR noise and symbols not suitable for audio
5. Failure handling:
   - if schema validation fails, keep the step in `draft`
   - if similarity score exceeds threshold, reject and regenerate or require manual rewrite
   - if rewrite quality remains poor after retry budget, the example stays unpublished

This design intentionally treats rewrite quality as reviewable generated content, not as guaranteed automation.

## Similarity Guardrail

To reduce the chance of near-verbatim publication, the builder should run an automated similarity check between source text and final narration.

Phase-1 rule:

1. Compute a text-overlap or edit-distance-style score after rewrite.
2. Record the result as `rewrite_similarity_score`.
3. Reject publication when the score exceeds the editorial threshold.
4. Human review remains mandatory even when the score passes.

## Editorial Review Workflow

Phase 1 review remains file-based, not CMS-based.

Recommended directories:

```text
data/tutorial_drafts/
data/tutorials_published/
```

Workflow:

1. Builder generates draft JSON plus audio assets.
2. Reviewer reads draft files and listens to audio locally.
3. Reviewer checks copyright safety, spoken quality, and lesson clarity.
4. Approved items are published into the public package.

Required review checklist:

1. No source-book identity leakage
2. No near-verbatim reproduction
3. Spoken narration sounds natural
4. Step sequence teaches a coherent concept
5. Audio assets are present and playable
6. Screenshot output is sanitized and does not retain unnecessary source-identifying page furniture

## Error Handling

### Offline builder

1. If rewrite fails for a step, keep the example in `draft` and block publish.
2. If TTS fails, keep the draft but block publication for that example.
3. If a screenshot is missing, mark the step as blocked rather than silently dropping it.
4. If similar source sections conflict, keep them as separate examples under one topic rather than over-merging.

### Publish

Publish should be atomic:

1. Build the next package version in a staging directory.
2. Validate the full package.
3. Write a versioned package directory such as `data/tutorials_published/versions/vNNN/`.
4. Update a single active manifest pointer only after validation succeeds.

Phase-1 publish switch strategy:

1. The online tutorial loader reads from a fixed `active.json` manifest file.
2. Publishing writes a new version directory, validates it fully, then atomically replaces `active.json`.
3. The online service reloads the active manifest on process start and on explicit refresh, not on every request.
4. Phase 1 may use manual process restart as the refresh trigger after publication.

### Online app

1. Missing topic or example returns 404, not silent empty success.
2. Missing user progress falls back to empty progress state.
3. Unsupported `board_mode` should fail explicitly rather than render incorrectly.
4. If an example is already completed, reopening resumes from the first step by default while still showing completion state.

## Progress Semantics

Phase-1 progress behavior:

1. When the user reaches the final step, the frontend marks the example as completed.
2. Progress is saved when the current step changes and again when completion occurs.
3. `last_step_id` represents the latest visited step, not a full per-step history.
4. Phase 1 does not store `completed_steps[]`.
5. Reopening a completed example starts from step 1 unless the user explicitly resumes from the previous step in a later phase.

## Testing Strategy

### Builder tests

1. `book.json -> source fragments` extraction behaves deterministically.
2. Topic dedupe rules produce stable IDs and grouping.
3. Published packages exclude forbidden fields.
4. Step payloads preserve image/audio/board consistency.
5. Publish validation rejects incomplete examples.
6. Rebuilds preserve `topic_id` and `example_id` for unchanged editorial units.
7. Similarity guardrails reject over-close rewrites.
8. Screenshot sanitization removes expected page-furniture regions for fixture inputs.

### Backend tests

1. Tutorial endpoints return the expected schema.
2. Not-found behavior is explicit.
3. Index refresh logic handles package updates safely.
4. Progress persistence behaves correctly for partial and completed examples.
5. Active manifest switching does not expose partial publish state.

### Frontend tests

1. Sidebar and route wiring expose the tutorial module.
2. Category -> topic -> example navigation works.
3. Example playback advances between steps correctly.
4. Audio and progress state stay in sync.
5. `board_mode=image` renders screenshots correctly.
6. Completed example re-entry behavior matches the defined progress semantics.

## Acceptance Criteria

Phase 1 is acceptable when:

1. One category, one topic, and at least one multi-step example can be published end to end.
2. The lesson can be browsed inside Galaxy as a dedicated module.
3. The example page supports picture plus narrated audio playback.
4. The public app and public APIs do not expose book identity or raw source text.
5. The publish process requires explicit human approval.
6. The public `Step` model remains compatible with a future SGF-backed renderer.
7. Rebuilding unchanged content does not invalidate saved progress IDs.

## Key Decisions Captured

1. The tutorial module is a new Galaxy module, not an extension of Play, Live, or Tsumego.
2. Phase 1 is Web-only.
3. Content generation is offline, not online.
4. Manual review is required before publication.
5. Public lessons are topic-centric, not book-centric.
6. Screenshots are acceptable in phase 1; SGF is a later upgrade.
7. CosyVoice is a TTS dependency, not an editorial engine.
8. Phase-1 publish refresh may use manual service restart after atomic manifest switch.
9. Phase-1 rewrite is LLM-assisted but schema-constrained and human-reviewed.

## Open Follow-up

These are implementation details, not blockers for the design:

1. Exact topic dedupe heuristics
2. Whether topic dedupe starts with deterministic rules only or adds embedding-based suggestions
3. Whether tutorial progress should require authentication or support anonymous local progress
4. Whether assets are served directly from disk or indexed through an asset manifest
5. Whether the first release should show estimated lesson duration on topic and example cards

Recommended starting point for topic dedupe:

1. First pass: deterministic normalization plus editorial mapping rules
2. Optional assist: similarity scoring or embedding suggestions for reviewer attention
3. If duplication is uncertain, do not merge automatically; keep separate examples or topics until reviewed
