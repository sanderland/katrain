-- Migration: Add video metadata columns to tutorial_figures
-- Run: psql -U katrain_user -d katrain_db -f scripts/migrate_video_fields.sql

ALTER TABLE tutorial_figures ADD COLUMN IF NOT EXISTS video_asset VARCHAR(512);
ALTER TABLE tutorial_figures ADD COLUMN IF NOT EXISTS video_duration_ms INTEGER;
ALTER TABLE tutorial_figures ADD COLUMN IF NOT EXISTS video_size_bytes INTEGER;
