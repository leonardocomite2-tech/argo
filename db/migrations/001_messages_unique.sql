CREATE UNIQUE INDEX IF NOT EXISTS messages_thread_canale_direzione_uniq
ON messages (thread_id, canale, direzione)
WHERE thread_id IS NOT NULL;
