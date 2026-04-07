---
name: tutorial-data-sync
description: Sync tutorial database tables and page assets from local Macbook to remote server fan@home-ubuntu. Use when deploying updated tutorial data (books, figures, narrations, board_payload, training samples) to the production server after local edits.
---

# Tutorial Data Sync (Local -> Remote)

## Overview

Full sync of tutorial module data from the local Macbook (PostgreSQL via Docker) to the remote server `fan@home-ubuntu` (same Docker PostgreSQL setup). Syncs both database records (5 tables) and asset files (page images, debug images, audio).

## Environment

| | Local (Macbook) | Remote (home-ubuntu) |
|--|--|--|
| **SSH** | - | `home-ubuntu` (see `~/.ssh/config`) |
| **Repo** | `/Users/fan/Repositories/katrain-tutorials` | `/home/fan/Repositories/katrain` |
| **Branch** | `feature/tutorials` | `develop` |
| **DB** | Docker `katrain-postgres`, user `katrain_user`, db `katrain_db` | Same |
| **Assets** | `data/tutorial_assets/` | `data/tutorial_assets/` (volume-mounted into `katrain-web` at `/app/data/tutorial_assets:ro`) |

## Sync Process

### Step 1: Export local DB (with column names for schema safety)

```bash
docker exec katrain-postgres pg_dump -U katrain_user -d katrain_db \
  --data-only --column-inserts \
  -t tutorial_books -t tutorial_chapters -t tutorial_sections \
  -t tutorial_figures -t training_samples \
  > tutorial_data.sql
```

### Step 2: Rsync assets (run in background, incremental)

```bash
rsync -avz data/tutorial_assets/ home-ubuntu:~/Repositories/katrain/data/tutorial_assets/
```

### Step 3: Upload SQL and import on remote

```bash
scp tutorial_data.sql home-ubuntu:~/tutorial_data.sql

# Truncate then import (foreign keys require cascade)
ssh home-ubuntu "docker exec -i katrain-postgres psql -U katrain_user -d katrain_db \
  -c 'TRUNCATE training_samples, tutorial_figures, tutorial_sections, tutorial_chapters, tutorial_books CASCADE;' \
  && docker exec -i katrain-postgres psql -U katrain_user -d katrain_db < ~/tutorial_data.sql"
```

### Step 4: Verify counts match

```bash
# Run on both local and remote, compare output
docker exec katrain-postgres psql -U katrain_user -d katrain_db -c \
  "SELECT 'books', COUNT(*) FROM tutorial_books UNION ALL \
   SELECT 'chapters', COUNT(*) FROM tutorial_chapters UNION ALL \
   SELECT 'sections', COUNT(*) FROM tutorial_sections UNION ALL \
   SELECT 'figures', COUNT(*) FROM tutorial_figures UNION ALL \
   SELECT 'training_samples', COUNT(*) FROM training_samples;"
```

## Tables Synced

| Table | Content |
|-------|---------|
| `tutorial_books` | Book metadata (title, author, slug, category) |
| `tutorial_chapters` | Chapter hierarchy |
| `tutorial_sections` | Section hierarchy |
| `tutorial_figures` | Figures with board_payload, narration, audio_asset, bbox, recognition_debug |
| `training_samples` | ML training patches from human-verified figures |

## Important Notes

- Use `--column-inserts` (not `--inserts`) because local and remote schemas may have different column order (e.g., `recognition_debug` column position differs between branches).
- `pg_dump` automatically appends `setval` calls to reset sequences, preventing ID conflicts on future inserts.
- rsync is incremental; only changed files are transferred. First sync ~387MB, subsequent syncs much faster.
- The remote `katrain-web` Docker container must have `./data/tutorial_assets:/app/data/tutorial_assets:ro` volume mount in `docker-compose.yml`. If images don't load after sync, check this mount.
- Clean up temp files after sync: `rm tutorial_data.sql; ssh home-ubuntu "rm ~/tutorial_data.sql"`

## Troubleshooting

### Images not loading on remote web UI
The `katrain-web` container needs the volume mount. Add to `docker-compose.yml` under `katrain-web`:
```yaml
volumes:
  - ./data/tutorial_assets:/app/data/tutorial_assets:ro
```
Then `docker compose up -d katrain-web` to recreate the container.

### Schema mismatch errors during import
If you see `invalid input syntax` errors, the column order differs. Ensure export uses `--column-inserts`. Minor type differences (`jsonb` vs `json`) are compatible.

### SSH connection refused
The remote host `home-ubuntu` is configured via `~/.ssh/config` (port forwarding). Do not use `fan@ubuntu` directly.
