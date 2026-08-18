# Argo

Servizio a eventi su VPS. FastAPI + Postgres + worker + Caddy in Docker Compose.
Cantiere attivo: 1 — poster. **Zero LLM.** Se serve un modello, fermati e chiedi.

## Invarianti (non violare mai)
- Ogni evento entrante ha una `dedup_key`. Ogni handler deve poter girare due volte senza danni.
- Ogni messaggio in uscita è scritto in `messages` PRIMA dell'invio.
- Nessun invio automatico di messaggi redatti da un LLM: tutto passa da `approvals`. Eccezione: le email transazionali con testo fisso, verso chi ha appena richiesto qualcosa (es. conferma poster all'host), partono dirette — non c'è nulla da approvare e approvare 200 volte la stessa email identica non è controllo, è rumore. Restano comunque loggate in `messages` prima dell'invio.
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

## Tono delle comunicazioni verso host e prospect (deciso 18/08)
Si dà del **lei**, ma senza formalismi da ufficio.
- Sì: "Buongiorno", "in allegato trova", "risponda pure a questa email"
- No: "Gentile Signore", "La preghiamo di voler cortesemente", "Distinti saluti"
Regola pratica: come si scriverebbe a un cliente che si stima ma non si conosce
ancora. Cordiale, diretto, mai rigido.
Vale per email, SMS e ogni messaggio in uscita, su tutti i canali.
