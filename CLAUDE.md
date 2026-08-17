# Argo

Servizio a eventi su VPS. FastAPI + Postgres + worker + Caddy in Docker Compose.
Cantiere attivo: 1 — poster. **Zero LLM.** Se serve un modello, fermati e chiedi.

## Invarianti (non violare mai)
- Ogni evento entrante ha una `dedup_key`. Ogni handler deve poter girare due volte senza danni.
- Ogni messaggio in uscita è scritto in `messages` PRIMA dell'invio.
- Nessun invio automatico: tutto passa da `approvals`.
- Segreti solo da variabili d'ambiente. Mai nel codice, mai nei log.
- Niente ORM, niente Alembic, niente astrazioni al primo uso. psycopg diretto.

## Comandi
docker compose up -d --build
docker compose logs api --tail 50
docker exec -it argo-db-1 psql -U argo -d argo

## Modo di lavorare
Proponi sempre la versione più piccola che funziona.
Quando manca un dato, chiedilo. Non riempirlo con un'assunzione plausibile.

## Stato del progetto
Leggi sempre STATO.md all'inizio della sessione.
