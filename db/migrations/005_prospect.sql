ALTER TABLE contacts ADD COLUMN IF NOT EXISTS telefono TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS sito TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS indirizzo TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS fonte TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS fonte_dettaglio TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS attributi JSONB;

CREATE TABLE IF NOT EXISTS soppressioni (
  id          SERIAL PRIMARY KEY,
  tipo        TEXT NOT NULL,
  valore      TEXT NOT NULL,
  motivo      TEXT,
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE (tipo, valore)
);
