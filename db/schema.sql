CREATE TABLE IF NOT EXISTS contacts (
  id             SERIAL PRIMARY KEY,
  ghl_contact_id TEXT UNIQUE,
  email          TEXT,
  nome           TEXT,
  stato          TEXT DEFAULT 'nuovo',
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS identities (
  id          SERIAL PRIMARY KEY,
  contact_id  INT REFERENCES contacts(id),
  canale      TEXT NOT NULL,
  external_id TEXT NOT NULL,
  UNIQUE (canale, external_id)
);

CREATE TABLE IF NOT EXISTS events (
  id          SERIAL PRIMARY KEY,
  tipo        TEXT NOT NULL,
  dedup_key   TEXT UNIQUE NOT NULL,
  payload     JSONB NOT NULL,
  contact_id  INT REFERENCES contacts(id),
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
  id          SERIAL PRIMARY KEY,
  contact_id  INT REFERENCES contacts(id),
  canale      TEXT NOT NULL,
  direzione   TEXT NOT NULL,
  thread_id   TEXT,
  testo       TEXT,
  categoria   TEXT,
  confidence  REAL,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS approvals (
  id            SERIAL PRIMARY KEY,
  message_id    INT REFERENCES messages(id),
  bozza         TEXT NOT NULL,
  stato         TEXT DEFAULT 'in_attesa',
  testo_finale  TEXT,
  tg_message_id BIGINT,
  created_at    TIMESTAMPTZ DEFAULT now(),
  decided_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS jobs (
  id            SERIAL PRIMARY KEY,
  tipo          TEXT NOT NULL,
  payload       JSONB,
  stato         TEXT DEFAULT 'pending',
  tentativi     INT DEFAULT 0,
  ultimo_errore TEXT,
  run_after     TIMESTAMPTZ DEFAULT now(),
  created_at    TIMESTAMPTZ DEFAULT now()
);
