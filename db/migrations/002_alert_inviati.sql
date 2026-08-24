CREATE TABLE IF NOT EXISTS alert_inviati (
  chiave      TEXT PRIMARY KEY,
  created_at  TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE approvals ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();
