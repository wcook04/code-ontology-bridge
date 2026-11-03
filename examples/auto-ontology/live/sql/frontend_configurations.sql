-- Minimal stand-in for the Prisma-owned `frontend.configurations` table
-- (frontend/prisma/schema.prisma:68-75), which the backend reads for feature
-- flags. Without the Next.js frontend nobody creates it, so every flag reads as
-- disabled. This creates it and turns semantic compilation on.
CREATE SCHEMA IF NOT EXISTS frontend;
CREATE TABLE IF NOT EXISTS frontend.configurations (
  key        text PRIMARY KEY,
  value      text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);
INSERT INTO frontend.configurations (key, value) VALUES ('semantic_compilation_enabled', 'true')
ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now();
