ALTER TABLE experiences
  ADD COLUMN IF NOT EXISTS item_quantities JSONB NOT NULL DEFAULT '[]'::jsonb;
