# Tutorial Video Storage & Lazy Loading

## Problem

1. Video files exist on disk (`data/tutorial_assets/{slug}/video/fig_{id}.mp4`) but have no DB record. Frontend guesses video URLs by string-replacing `audio_asset` paths.
2. Opening a section page is slow because the browser eagerly downloads all video data (no `preload` control on `<video>` tags).
3. No Nginx layer — FastAPI serves video files through Python, which can't handle high concurrency.

## Design Decisions (from brainstorming)

| Decision | Choice |
|----------|--------|
| Video file storage | File system + DB stores path (same pattern as `audio_asset`) |
| New DB fields | `video_asset` + `video_duration_ms` + `video_size_bytes` |
| Frontend optimization | `<video preload="none">` — download only on play |
| High concurrency serving | Nginx serves `/api/v1/tutorials/assets/` directly (future step) |

---

## Step 1: Add DB columns to TutorialFigure

**File**: `katrain/web/core/models_db.py` (line ~356)

Add after `audio_asset`:
```python
audio_asset = Column(String(512), nullable=True)
video_asset = Column(String(512), nullable=True)          # NEW
video_duration_ms = Column(Integer, nullable=True)         # NEW
video_size_bytes = Column(Integer, nullable=True)          # NEW
order = Column(Integer, nullable=False)
```

**Migration** (no Alembic in project — direct SQL):
```sql
ALTER TABLE tutorial_figures ADD COLUMN video_asset VARCHAR(512);
ALTER TABLE tutorial_figures ADD COLUMN video_duration_ms INTEGER;
ALTER TABLE tutorial_figures ADD COLUMN video_size_bytes INTEGER;
```

Run on server: `psql -U katrain_user -d katrain_db -f migration.sql`

---

## Step 2: Update Pydantic schemas

**File**: `katrain/web/tutorials/models.py`

### TutorialFigureOut (line ~54)
Add after `audio_asset`:
```python
audio_asset: Optional[str] = None
video_asset: Optional[str] = None          # NEW
video_duration_ms: Optional[int] = None    # NEW
video_size_bytes: Optional[int] = None     # NEW
order: int
```

### NarrationUpdate (line ~143)
Add:
```python
narration: str
audio_asset: Optional[str] = None
video_asset: Optional[str] = None          # NEW
video_duration_ms: Optional[int] = None    # NEW
video_size_bytes: Optional[int] = None     # NEW
```

---

## Step 3: Update generate_video.py to write DB fields

**File**: `scripts/generate_video.py` — `process_figure()` function (line ~776)

After `compose_final_video(...)`, before `print("Done!")`:
```python
# Write video metadata to DB
figure.video_asset = f"tutorial_assets/{book_slug}/video/fig_{figure_id}.mp4"
figure.video_duration_ms = timeline["total_duration_ms"]
figure.video_size_bytes = video_path.stat().st_size
db.commit()
print(f"  DB updated: video_asset={figure.video_asset}")
```

Also add a backfill script/command to populate existing videos:
```python
# In process_figure(), when video already exists and not --force:
if video_path.exists() and not force:
    # Still update DB if fields are empty (backfill)
    if not figure.video_asset:
        figure.video_asset = f"tutorial_assets/{book_slug}/video/fig_{figure_id}.mp4"
        figure.video_duration_ms = ...  # ffprobe to get duration
        figure.video_size_bytes = video_path.stat().st_size
        db.commit()
    return
```

---

## Step 4: Frontend — use video_asset from API, add preload="none"

### 4a. Update TypeScript types

**File**: `katrain/web/ui/src/galaxy/api/tutorialApi.ts`

Add to the Figure type (matching Pydantic schema):
```typescript
video_asset?: string | null;
video_duration_ms?: number | null;
video_size_bytes?: number | null;
```

### 4b. TutorialFigurePage — use video_asset, add preload="none"

**File**: `katrain/web/ui/src/galaxy/pages/tutorials/TutorialFigurePage.tsx` (line ~371-383)

Before (guesses URL from audio path):
```tsx
{currentFigure.audio_asset && (() => {
  const videoUrl = TutorialAPI.assetUrl(
    currentFigure.audio_asset!.replace('/audio/', '/video/').replace('.mp3', '.mp4')
  );
  return (
    <video controls width="100%" src={videoUrl}
      onError={(e) => { (e.target as HTMLVideoElement).style.display = 'none'; }}
    />
  );
})()}
```

After (uses DB field, lazy loading):
```tsx
{currentFigure.video_asset && (
  <Box sx={{ mt: 2 }}>
    <video
      controls
      preload="none"
      width="100%"
      style={{ borderRadius: 8, maxHeight: 400 }}
      src={TutorialAPI.assetUrl(currentFigure.video_asset)}
      onError={(e) => { (e.target as HTMLVideoElement).style.display = 'none'; }}
    />
    {currentFigure.video_duration_ms && (
      <Typography variant="caption" color="text.secondary">
        {Math.floor(currentFigure.video_duration_ms / 60000)}:
        {String(Math.floor((currentFigure.video_duration_ms % 60000) / 1000)).padStart(2, '0')}
      </Typography>
    )}
  </Box>
)}
```

### 4c. TutorialBookDetailPage — add preload="none" to section video

**File**: `katrain/web/ui/src/galaxy/pages/tutorials/TutorialBookDetailPage.tsx` (line ~143)

```tsx
<video controls autoPlay preload="none" ...>
```

---

## Step 5: Nginx static file serving (production optimization)

**File**: New `nginx/tutorials.conf` or add to existing server block

```nginx
# Serve tutorial assets directly (bypass Python for static files)
location /api/v1/tutorials/assets/tutorial_assets/ {
    alias /app/data/tutorial_assets/;
    expires 7d;
    add_header Cache-Control "public, immutable";
    add_header Accept-Ranges bytes;  # Enable range requests for video seeking
}
```

**Docker**: Add Nginx service to `docker-compose.yml` or configure existing reverse proxy.

> Note: This step is optional — the system works without it. Only needed when concurrent users > ~500.

---

## File Change Summary

| File | Change |
|------|--------|
| `katrain/web/core/models_db.py` | Add 3 columns to TutorialFigure |
| `katrain/web/tutorials/models.py` | Add 3 fields to TutorialFigureOut + NarrationUpdate |
| `scripts/generate_video.py` | Write video_asset/duration/size to DB after generation |
| `katrain/web/ui/src/galaxy/api/tutorialApi.ts` | Add video fields to TS types |
| `katrain/web/ui/src/galaxy/pages/tutorials/TutorialFigurePage.tsx` | Use video_asset, add preload="none" |
| `katrain/web/ui/src/galaxy/pages/tutorials/TutorialBookDetailPage.tsx` | Add preload="none" to section video |
| SQL migration script | ALTER TABLE add 3 columns |

## Execution Order

1. **DB migration** (SQL) — add columns, zero downtime
2. **Backend models** (models_db.py + models.py) — expose new fields
3. **generate_video.py** — write metadata on generation + backfill existing
4. **Frontend** — use video_asset, preload="none"
5. **Nginx** (optional) — static file serving for high concurrency

## Deployment Notes (from local Macbook testing)

### 1. DB migration must run BEFORE restarting the app

After deploying the code, SQLAlchemy will immediately try to SELECT the new columns. If the migration hasn't run, **all tutorial API requests will crash** with:

```
psycopg2.errors.UndefinedColumn: column tutorial_figures.video_asset does not exist
```

**Fix**: Run migration first, then restart:
```bash
psql -U katrain_user -d katrain_db -f scripts/migrate_video_fields.sql
```

If `psql` is not available (e.g. inside Docker), use Python:
```python
from katrain.web.core.db import SessionLocal
from sqlalchemy import text
db = SessionLocal()
db.execute(text('ALTER TABLE tutorial_figures ADD COLUMN IF NOT EXISTS video_asset VARCHAR(512)'))
db.execute(text('ALTER TABLE tutorial_figures ADD COLUMN IF NOT EXISTS video_duration_ms INTEGER'))
db.execute(text('ALTER TABLE tutorial_figures ADD COLUMN IF NOT EXISTS video_size_bytes INTEGER'))
db.commit()
db.close()
```

### 2. Existing videos will disappear until DB is backfilled

The old frontend code guessed video URLs from `audio_asset` paths (`replace('/audio/', '/video/')`). The new code uses `video_asset` from the DB. After migration, `video_asset` is `NULL` for all existing figures, so **videos won't render**.

**Fix**: Run backfill after migration:
```python
from katrain.web.core.db import SessionLocal
from katrain.web.core.models_db import TutorialFigure
from pathlib import Path

db = SessionLocal()
REPO = Path('/app')  # adjust to server repo root

figures = db.query(TutorialFigure).filter(
    TutorialFigure.audio_asset.isnot(None),
    TutorialFigure.video_asset.is_(None)
).all()

updated = 0
for fig in figures:
    parts = fig.audio_asset.split('/')
    if len(parts) < 2:
        continue
    book_slug = parts[1]
    video_path = REPO / 'data' / 'tutorial_assets' / book_slug / 'video' / f'fig_{fig.id}.mp4'
    if video_path.exists():
        fig.video_asset = f'tutorial_assets/{book_slug}/video/fig_{fig.id}.mp4'
        fig.video_size_bytes = video_path.stat().st_size
        updated += 1

db.commit()
db.close()
print(f'Backfilled {updated} figures')
```

### Deployment order summary

1. **Stop app** (or accept brief downtime)
2. **Run DB migration** (ALTER TABLE)
3. **Deploy code** (git pull / Docker rebuild)
4. **Start app**
5. **Run backfill** (populate video_asset for existing videos)

---

## Verification

1. `python scripts/generate_video.py --figure-id 2 --force` — verify DB fields populated
2. `psql -c "SELECT id, video_asset, video_duration_ms, video_size_bytes FROM tutorial_figures WHERE video_asset IS NOT NULL"`
3. Open browser → tutorial figure page → video should NOT auto-download (check Network tab)
4. Click play → video loads and plays
5. Check API response includes `video_asset` field: `curl localhost:8001/api/v1/tutorials/sections/1 | jq '.figures[0].video_asset'`
