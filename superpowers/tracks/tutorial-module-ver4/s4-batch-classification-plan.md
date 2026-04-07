# S4 Batch Classification: Reduce Token Waste

**Goal:** Replace per-patch VLLM API calls with batch requests to eliminate redundant prompt tokens.

**Date:** 2026-03-30

**Status:** ABANDONED — batch mode dramatically degrades classification quality.

## Experiment Results (2026-03-30)

Tested on section 6 "问题1. 外势的价值" (6 figures, 146 patches, 105 ambiguous).

| Metric | Per-Patch (current) | Batch |
|--------|-------------------|-------|
| Overall accuracy | **132/146 (90.4%)** | 80/146 (54.8%) |
| Ambiguous-only accuracy | **92/105 (87.6%)** | 40/105 (38.1%) |
| Input tokens (est.) | 38,220 (105×364) | ~3,216 (6×536) |
| Token savings | — | 91.6% reduction |
| Latency | ~46s (105 calls/4 threads) | 17.2s (6 calls) |

**Root cause:** Haiku systematically misclassifies white stones as "empty" in multi-image batch context. White stones (open circles with thin borders) are visually similar to empty grid intersections, and the model loses discrimination ability when processing 10-25 small patches simultaneously. This is the dominant failure mode — nearly every white stone was classified as "empty".

**Conclusion:** Token savings (91.6%) and latency improvement (2.7×) are significant, but accuracy drops from 87.6% → 38.1% on the patches that matter most (ambiguous ones needing VLLM). The per-patch cost is already low (~$0.03/section at Haiku rates), so the optimization is not worth the quality loss. Keeping per-patch classification.

## Problem

Current S4 sends **one API call per ambiguous patch**, each repeating the identical 342-token classification prompt:

```
Per figure:  ~10 ambiguous patches × (342 prompt + ~200 image) = ~5,420 tokens
Per section: ~62 API calls × 342 prompt tokens = ~21,000 wasted prompt tokens
```

The prompt is identical across all patches — only the image changes. With Haiku at $0.80/M input tokens this is cheap in absolute terms, but the **latency** of 10+ sequential API calls per figure (even with 4-thread concurrency) is the bigger cost: ~2-5 seconds per figure.

## Approach: Multi-Image Single Request

Send all ambiguous patches for one figure in a **single API call** with multiple image blocks. The model classifies all patches at once and returns structured output.

### Why this approach

| Approach | Token savings | Quality risk | Complexity |
|----------|--------------|-------------|------------|
| **Multi-image batch** | ~90% prompt reduction | Low — patches still separate images | Low |
| Contact sheet grid | ~95% (1 image) | Medium — small patches in grid may confuse model | Medium |
| Prompt caching | 0% (prompt < 4096 min) | None | N/A |
| Anthropic Batch API | 50% cost (async) | None | Medium — async flow |

Multi-image batch is the best trade-off: near-maximum token savings, minimal quality risk, simplest implementation.

### Before (current)

```
Call 1: [image_A] + prompt (342 tok) → "white"
Call 2: [image_B] + prompt (342 tok) → "black+3"
...
Call N: [image_N] + prompt (342 tok) → "empty"

Total: N calls, N × 342 = 3,420 prompt tokens (N=10)
Latency: N/4 round trips (4 threads)
```

### After (proposed)

```
Call 1: [image_A] + [image_B] + ... + [image_N] + batch_prompt (400 tok) → JSON
  {"A": "white", "B": "black+3", ..., "N": "empty"}

Total: 1 call, ~400 prompt tokens
Latency: 1 round trip
```

## Tasks

### Task 1: Create `haiku_classify_batch()` function

**File:** `scripts/recognize_boards_v2.py` (add after `haiku_classify_patch`)

```python
def haiku_classify_batch(patch_map: dict[str, Path], max_retries=3) -> dict[str, str]:
    """Classify multiple patches in a single Haiku API call.

    patch_map: {label: patch_image_path} e.g. {"A": Path("...A_2_13.png"), "B": ...}
    Returns: {label: classification} e.g. {"A": "white", "B": "black+3"}
    """
```

**Implementation details:**
1. Build message content as: `[image_A, text_"A:", image_B, text_"B:", ..., text_prompt]`
   - Each image tagged with its label so the model knows which is which
   - Final text block contains the classification prompt + output format instruction
2. Prompt modification (append to `HAIKU_CLASSIFY_PROMPT`):
   ```
   You are given multiple patches, each preceded by its label (A, B, C...).
   Classify each one. Output ONLY a JSON object mapping label to classification.
   Example: {"A": "white+2", "B": "black", "C": "empty"}
   ```
3. Parse JSON response, fallback to per-patch if JSON parsing fails
4. Same retry logic as current `haiku_classify_patch`
5. `max_tokens` should be `len(patch_map) * 15` (enough for JSON output)

**Edge cases:**
- If > 20 patches (rare), split into batches of 20 (API image limit)
- If JSON parse fails, log warning and fall back to `haiku_classify_patch` per-patch
- Empty patch_map → return empty dict

### Task 2: Create `qwen_classify_batch()` and `gemini_classify_batch()`

Same pattern as Task 1, adapted for each backend's API format:
- **Qwen**: OpenAI-compatible, multiple `image_url` blocks in one message
- **Gemini**: OpenAI-compatible, same structure

Both use identical prompt modification and JSON parsing logic.

**Shared helper:** Extract a `_parse_batch_response(text, labels)` function:
```python
def _parse_batch_response(text: str, labels: list[str]) -> dict[str, str]:
    """Parse JSON batch classification response. Returns {label: classification}."""
    # Try JSON parse
    # Normalize each value (lowercase, strip, letter_ handling)
    # Return only labels that were requested
```

### Task 3: Wire batch functions into `process_page()`

**File:** `scripts/recognize_boards_v2.py`, inside the S4 block (~line 1299)

Replace:
```python
classify_fn = {"haiku": haiku_classify_patch, ...}[vllm]
# ... ThreadPoolExecutor loop calling classify_fn per patch
```

With:
```python
batch_fn = {"haiku": haiku_classify_batch, "qwen": qwen_classify_batch, "gemini": gemini_classify_batch}[vllm]
# ... single call: results = batch_fn(patch_map)
```

**Keep the old per-patch path as fallback** — if batch returns fewer results than expected (JSON parse failure), retry missing labels with per-patch calls.

### Task 4: Update `classification_source` tracking

Currently `classification_source` is just `"haiku"` / `"qwen"` / `"gemini"`. Update to include batch indicator:
- `"haiku_batch"` for batch mode
- `"haiku"` for fallback per-patch

This helps track which method was used in training data export.

### Task 5: Test and compare

Run on section 6 (问题1. 外势的价值) with each backend:
```bash
# Haiku batch
python scripts/recognize_boards_v2.py --section-id 6 --force

# Compare with old per-patch (add --no-batch flag for testing)
python scripts/recognize_boards_v2.py --section-id 6 --force --no-batch
```

**Verify:**
1. Same or better classification accuracy vs per-patch
2. Token usage reduction (check `response.usage`)
3. Latency improvement (log elapsed time for S4 step)
4. Fallback works when JSON parsing fails

## Risks

| Risk | Mitigation |
|------|-----------|
| Model confuses patches when seeing many at once | Label each image clearly; test with 5, 10, 20 patches |
| JSON output sometimes malformed | Regex fallback parser + per-patch retry |
| Anthropic API max images per request | Split into batches of 20 if needed |
| Batch mode changes classification quality | A/B test on section 6, compare B/W/label counts |

## Files to Modify

| Action | File |
|--------|------|
| **Edit** | `scripts/recognize_boards_v2.py` — add batch functions, wire into S4 |

## Out of Scope

- Prompt caching (prompt too short for Haiku's 4096 minimum)
- Anthropic Batch API (async complexity not worth it for <100 calls)
- Contact sheet approach (quality risk outweighs marginal savings over multi-image)
- Changing the classification prompt itself
