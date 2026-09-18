-- Quota gratuita OpenRouter del giorno (18/9/2026). Tabella sua, non una
-- colonna di llm_chiamate_giorno: la spesa Anthropic e la quota gratuita
-- sono limiti diversi e non devono mai finire nella stessa somma. Una riga
-- per giorno (fuso Europe/Rome), incrementata PRIMA di ogni richiesta con
-- INSERT ... ON CONFLICT DO UPDATE ... RETURNING (connectors/psql_host.py):
-- le richieste fallite consumano la quota di OpenRouter, quindi contano.
CREATE TABLE IF NOT EXISTS openrouter_chiamate_giorno (
  giorno    DATE PRIMARY KEY,
  chiamate  INTEGER NOT NULL
);
