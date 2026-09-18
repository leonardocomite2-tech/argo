-- Finestra di conversazione di Argo (cantiere Argo — il ponte, passo 4):
-- i messaggi liberi di Leonardo al bot Argo e le risposte di Argo, per
-- dare al ramo conversazionale gli ultimi scambi anche dopo un riavvio
-- (il consumer host è un processo nuovo a ogni minuto, niente memoria).
-- tg_message_id UNIQUE è il claim atomico contro la redelivery Telegram
-- dello stesso messaggio (NULL sulle righe di Argo, che non ne hanno uno).
CREATE TABLE IF NOT EXISTS conversazione_argo (
  id             SERIAL PRIMARY KEY,
  created_at     TIMESTAMPTZ DEFAULT now(),
  ruolo          TEXT NOT NULL,
  testo          TEXT NOT NULL,
  tg_message_id  BIGINT UNIQUE
);
