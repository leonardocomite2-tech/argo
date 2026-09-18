-- Contatore persistente del tetto giornaliero LLM (cantiere Argo — il
-- ponte, passo 4bis). Il consumer host di Argo è un processo nuovo a ogni
-- minuto: il contatore in-memory di connectors/llm.py ripartiva da 0 a ogni
-- job e LLM_TETTO_GIORNALIERO non scattava mai. Una riga per giorno (fuso
-- Europe/Rome), incrementata in modo atomico con INSERT ... ON CONFLICT DO
-- UPDATE ... RETURNING. Il worker Docker non la usa (resta in-memory).
CREATE TABLE IF NOT EXISTS llm_chiamate_giorno (
  giorno    DATE PRIMARY KEY,
  chiamate  INTEGER NOT NULL
);
