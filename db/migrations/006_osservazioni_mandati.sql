CREATE TABLE IF NOT EXISTS osservazioni (
  id                SERIAL PRIMARY KEY,
  created_at        TIMESTAMPTZ DEFAULT now(),
  dedup_key         TEXT UNIQUE NOT NULL,
  fonte             TEXT NOT NULL,
  severita          TEXT NOT NULL,
  contratto_toccato TEXT,
  testo             TEXT NOT NULL,
  stato             TEXT NOT NULL DEFAULT 'nuova'
                    CHECK (stato IN ('nuova','riferita','archiviata'))
);

CREATE INDEX IF NOT EXISTS osservazioni_stato_idx ON osservazioni (stato);

CREATE TABLE IF NOT EXISTS mandati (
  id           SERIAL PRIMARY KEY,
  created_at   TIMESTAMPTZ DEFAULT now(),
  origine_msg  TEXT NOT NULL,
  tipo         TEXT NOT NULL CHECK (tipo IN ('consultazione','esecuzione')),
  oggetto      TEXT NOT NULL,
  vincoli      TEXT,
  esito        TEXT
);

CREATE INDEX IF NOT EXISTS mandati_esito_aperti_idx ON mandati (id) WHERE esito IS NULL;
