# Argo

Servizio a eventi su VPS. FastAPI + Postgres + worker + Caddy in Docker Compose.
Cantiere attivo: 2 — email. L'LLM è ammesso solo per classificare (enum chiuso
di categorie) e per redigere bozze. Mai per decidere se inviare, mai per
eseguire azioni. Ogni bozza passa da approvals. Nel dubbio, fermati e chiedi.

## Invarianti (non violare mai)
- Ogni evento entrante ha una `dedup_key`. Ogni handler deve poter girare due volte senza danni. Eccezione: i comandi dell'operatore (es. click sui bottoni Telegram) non sono eventi di dominio e non vanno in `events`. La loro idempotenza si ottiene con un claim atomico sulla riga che modificano — `UPDATE ... WHERE stato = <atteso> RETURNING id` — non con una `dedup_key`.
- Ogni messaggio in uscita è scritto in `messages` PRIMA dell'invio. Eccezione: le email operative verso l'operatore (backup, report di sistema) non vanno in `messages`. Quella tabella traccia le conversazioni con host e prospect, non il traffico interno del sistema.
- Nessun invio automatico di messaggi redatti da un LLM: tutto passa da `approvals`. Eccezione: le email transazionali con testo fisso verso chi ha avviato un flusso con noi (conferma poster, depliant di benvenuto, correzione codice) partono dirette, anche se differite nel tempo. Il criterio non è la vicinanza temporale ma l'assenza di giudizio: se il testo è deciso in anticipo e uguale per tutti, non c'è nulla da approvare. Serve approvals quando il contenuto è generato da un LLM o dipende dal caso specifico. Restano comunque loggate in `messages` prima dell'invio.
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

## Formato dei piani
Alla fine di ogni piano, aggiungi una sezione RIEPILOGO di massimo 15 righe:
file toccati, decisioni chiave, assunzioni fatte e problemi trovati.
Deve bastare da sola a capire il piano senza leggere il resto.

## Cambiare il formato di un campo esistente
Prima di cambiare **cosa può contenere** un campo (non lo schema, il contenuto),
cerca tutti i punti che lo leggono. Le assunzioni implicite non sono dichiarate
da nessuna parte e nessun guardrail le vede.
Caso reale (30/08): `thread_id` era implicitamente numerico. Renderlo
alfanumerico (`"1468:depliant"`) ha rotto otto query che facevano `::int`,
mandando il digest serale in loop di retry.
