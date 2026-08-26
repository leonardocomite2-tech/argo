# STATO — aggiornare a fine di ogni step

## Fatto
- VPS Hostinger KVM1, Ubuntu 24.04, Docker + Compose
- 4 container: caddy (HTTPS ok) · api (FastAPI, /health) · worker (poll jobs 5s) · db (Postgres)
- argo.narratour-review.com → certificato Let's Encrypt valido
- Schema DB: contacts, identities, events, messages, approvals, jobs
- Git init + primo commit. Claude Code 2.1.233 + CLAUDE.md + subagent guardrail-review

## In corso
(step 5 chiuso: media/poster.py con auto-fit font 80→20, box (994,2580)-(1423,2680),
font Montserrat-Bold.ttf scaricato da Google Fonts; worker/loop.py legge host_code da
events.payload->>'host_code' e genera /app/out/poster_<CODE>.png; volume posters
condiviso api+worker in docker-compose)
- Step 6: invio email con poster allegato implementato (host valido).
  Manca ancora: email di richiesta per host_code non valido (oggi il webhook
  risponde 422 prima di creare evento/job — da riconciliare).
- Step 7: notifiche Telegram (connectors/telegram.py, notifica() via urllib stdlib,
  mai solleva eccezioni). Collegata in tre punti: poster inviato con successo,
  job passato a failed, webhook 422 per host_code non valido (caratteri non validi
  o troppo lungo — entrambi i casi, mai il valore grezzo nel testo dell'alert).
  Significato cambiato dal 18/08: da "l'host è rimasto a mani vuote, intervieni"
  a "il form potrebbe essere rotto, ma l'host è già stato avvisato in automatico"
  — resta utile per capire che il JS non funziona, non è più urgente.

- Cantiere 2 — email: `connectors/imap_reader.py` (`leggi_nuove()`, stdlib
  puro: `imaplib`+`email`+`html.parser`) legge INBOX non letta su ogni casella
  configurata (`MAILBOX_N_USER/PASS`, N=1,2,... finché esistono) via
  `BODY.PEEK[]` (mai marca come letto). Casella rotta → log + alert Telegram
  (solo indirizzo + tipo eccezione, mai la password) e si prosegue con le altre.
  Nel worker: handler `leggi_email` (self-chaining, riaccoda il prossimo giro
  a +2 minuti solo dopo aver processato con successo tutti i messaggi — così
  un fallimento a metà non duplica la catena sui retry; logga a INFO quante
  email legge ad ogni giro) inserisce evento `email.reply` per messaggio
  (`dedup_key='imap:'+message_id`, o `imap-sint:`+hash se manca il
  Message-ID) e accoda `notifica_risposta`. `garantisci_leggi_email()` riaccoda il
  job se la catena si spezza (nessun `leggi_email` pending/running), sia
  all'avvio sia ad ogni giro del loop worker — protegge dal caso in cui
  l'handler vada in `failed` dopo i retry.
- Approvazione bozze via Telegram (`connectors/telegram.py`:
  `chiedi_approvazione()` manda bozza+contesto con tre bottoni inline
  (Approva/Modifica/Rifiuta, callback_data `appr:<id>`/`modif:<id>`/`rifiu:<id>`),
  `chiedi_testo_corretto()` manda un force_reply, `rispondi_callback()` chiude
  lo spinner del bottone con `answerCallbackQuery`. `POST /webhook/telegram` in
  `backend/main.py` verifica `X-Telegram-Bot-Api-Secret-Token` (401 se non
  combacia), poi gestisce `callback_query` e `message.reply_to_message`,
  risponde sempre 200 altrimenti. `approvals.stato`: `in_attesa` (default) ->
  `approvata` | `rifiutata` | `in_modifica` (transitorio, claimato mentre si
  aspetta la reply col testo corretto) -> `modificata`. Ogni transizione passa
  da un `UPDATE ... WHERE stato='<stato atteso>' RETURNING id` come guardia
  atomica di idempotenza (Telegram può consegnare lo stesso update due volte).
  Approva/Rifiuta/Modificata accodano il job `invia_risposta` (worker, ancora
  uno stub: se `rifiutata` non fa nulla, altrimenti logga il testo che
  invierebbe — l'invio vero arriva col drafter). Handler manuale
  `test_approvazione` per collaudare il giro senza classificatore.
- Alert operativi (`worker/loop.py`, handler `controlli_periodici`,
  self-chaining ogni 15 minuti + `garantisci_controlli_periodici()` come
  gli altri due cicli): tre controlli, ciascuno in try/except proprio così
  uno che fallisce non blocca gli altri né il self-chaining. Idempotenza per
  caso specifico con tabella `alert_inviati` (`chiave TEXT PRIMARY KEY`) e
  helper `_alert_una_volta()`, `INSERT ... ON CONFLICT DO NOTHING RETURNING`
  — ogni alert parte una volta sola.
  1. Approvazione bloccata: `in_attesa`/`in_modifica` da più di 6h, misurate
     su `approvals.updated_at` (nuova colonna, non `created_at` che non si
     muove dopo la creazione — altrimenti un Modifica tardivo falserebbe la
     soglia). `updated_at` aggiornata in tutti i punti di `backend/main.py`
     che cambiano `stato`. La sezione "approvazioni in attesa" del digest
     serale è stata allineata sullo stesso campo, per non mostrare due età
     diverse per lo stesso caso.
  2. Registrazione senza poster: evento `form.submitted` più vecchio di 30
     minuti senza riga `out` in `messages` sullo stesso `thread_id`.
  3. Volume anomalo: più di 50 eventi in `events` nell'ultima ora (soglia
     fissa, pensata per un loop di webhook — oggi non scatta mai).
  Migrazione: `db/migrations/002_alert_inviati.sql`.
- Lo stub `classifica_messaggio` è stato sostituito da `notifica_risposta`:
  legge mittente/destinatario/oggetto/testo dall'evento e manda una notifica
  Telegram formattata (oggetto assente -> "(senza oggetto)", testo troncato a
  400 caratteri con "[...]"). Guardia di idempotenza come gli altri handler:
  riga in `messages` (canale='email', direzione='in', thread_id=str(event_id),
  contact_id NULL) scritta prima della notifica. `migra_job_notifica_risposta()`,
  chiamata una volta all'avvio, converte eventuali job `classifica_messaggio`
  ancora pending (accodati prima del rename) al nuovo tipo. La classificazione
  LLM (enum chiuso di categorie) e la stesura di bozze restano da fare — questo
  handler resta solo notifica, zero LLM.

## Prossimi step (cantiere 1 — poster)
8. workflow GHL

## Cantiere 3 — DM Instagram/Facebook (avviato 26/08)
`POST /webhook/ghl/dm` in `backend/main.py`, per ora solo in modalità
ricognizione: verifica `X-Argo-Secret` (401 se non combacia), 422 se il
body non è un dict (stesso pattern di `/webhook/ghl/form`), poi logga a
INFO solo i *nomi* dei campi ricevuti (`sorted(body.keys())` e, se
`customData` è un dict, anche `sorted(customData.keys())` — mai i valori),
risponde sempre 200 così GHL non ritenta. Nessuna scrittura su
`events`/`jobs`: non conosciamo ancora la struttura del payload DM (diversa
da quella dei form), prima si osservano i log poi si scrive il connettore
vero.

## DECISIONI CHIUSE
- **QR e attribuzione** (era bloccante prima dello step 5): QR statico, uguale per
  tutti gli host, confermato testato e funzionante. L'attribuzione all'host non
  passa dal QR/URL ma dal codice sconto che il cliente digita sul sito — quindi
  nessun ?ref=CODICE necessario.
- **Guardia di idempotenza SELECT+INSERT su messages** (23/08): risolta con
  indice unico parziale `messages_thread_canale_direzione_uniq` su
  `(thread_id, canale, direzione) WHERE thread_id IS NOT NULL`
  (`db/migrations/001_messages_unique.sql` + `db/schema.sql`) e sostituendo,
  in `genera_poster`, `avvisa_codice_invalido`, `notifica_risposta` e
  `invia_risposta`, il SELECT+INSERT separato con un unico
  `INSERT ... ON CONFLICT (...) DO NOTHING RETURNING id`: la guardia ora è
  atomica a livello DB, niente più finestra tra verifica e scrittura.

## DECISIONI APERTE — bloccano
- Provider caselle Instantly + casella pulita: non blocca più il codice (il
  connettore IMAP è provider-agnostico, basta configurare `IMAP_HOST`/
  `MAILBOX_N_USER/PASS` in `.env`), resta aperta solo la scelta operativa di
  quale casella usare in produzione.
- (chiusa 18/08) Tono: lei cordiale, definito in CLAUDE.md
  questo step — `classifica_messaggio` per ora è solo uno stub)

## DATI MANCANTI
- poster_con_codice.png (stesse dimensioni, con codice esempio) — solo per confronto
  visivo, non serve alla generazione

## Note operative
- DNS: narratour-review.com → zona su HOSTINGER
        narra-tours.com     → zona su CLOUDFLARE
- Segreti in /root/argo/.env (mai committato)

## Codice non valido — comportamento deciso (17/08)
Codice > 10 caratteri o con caratteri fuori da [A-Z0-9]:
- NESSUN poster generato (mai stampare un codice che non esiste nel sistema)
- Email automatica all'host: codice non valido, spiegazione, invito a
  rispondere con un codice valido
- Alert Telegram a Leonardo
Motivo: un poster con codice sbagliato sembra giusto, l'host lo stampa e
lo appende. Il danno emerge settimane dopo, dai clienti.
Alert Telegram implementato (step 7). Email di richiesta implementata (18/08):
webhook non risponde più 422 per host_code vuoto/caratteri non validi/troppo
lungo, registra evento 'form.codice_invalido' + job 'avvisa_codice_invalido',
risponde 200. Restano 422 solo submission_id mancante e body non-dict.

### dedup_key include host_code (18/08)
GHL non espone un id di submission stabile: `submission_id` è sempre
`{{contact.id}}`, identico ad ogni ricompilazione dello stesso contatto.
Con `dedup_key = f"ghl:{submission_id}"` un secondo tentativo (anche con
codice corretto) veniva scartato dall'ON CONFLICT e il poster non arrivava
mai. Corretto: `dedup_key = f"ghl:{submission_id}:{host_code}"` per entrambi
gli eventi (form.submitted e form.codice_invalido).
Conseguenza voluta: un host che invia più codici validi diversi riceve un
poster per ciascuno (l'invariante "un poster per host" diventa "un poster
per host+codice"). Stesso contatto che rimanda lo stesso codice (valido o
vuoto) → scartato come prima, nessuna email duplicata.
