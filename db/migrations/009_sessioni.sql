-- Memoria delle sessioni di Claude Code (18/9/2026). Una riga per sessione,
-- scritta dagli hook SessionStart/SessionEnd (scripts/memoria/hook_sessione.py).
-- Affianca STATO.md, non lo sostituisce. dedup_key = 'claude-session:<id>':
-- lo stesso hook lanciato due volte aggiorna la riga, non ne crea un'altra.
-- Mai valori di variabili d'ambiente, password o token: i campi testo sono
-- ripuliti dai valori di .env prima della scrittura.
CREATE TABLE IF NOT EXISTS sessioni (
  id                  SERIAL PRIMARY KEY,
  created_at          TIMESTAMPTZ DEFAULT now(),
  dedup_key           TEXT UNIQUE NOT NULL,
  session_id          TEXT NOT NULL,
  inizio              TIMESTAMPTZ,
  fine                TIMESTAMPTZ,
  head_iniziale       TEXT,
  head_finale         TEXT,
  motivo_fine         TEXT,
  copertura           TEXT,
  cantieri            TEXT[],
  file_toccati        TEXT[],
  commit              JSONB,
  correzioni_manuali  TEXT[],
  sospesi_aperti      JSONB,
  sospesi_chiusi      JSONB,
  sessioni_parallele  TEXT[],
  decisioni           TEXT,
  decisioni_stato     TEXT
);
