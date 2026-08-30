# STATO — aggiornare a fine di ogni step

## Fatto
- VPS Hostinger KVM1, Ubuntu 24.04, Docker + Compose
- 4 container: caddy (HTTPS ok) · api (FastAPI, /health) · worker (poll jobs 5s) · db (Postgres)
- argo.narratour-review.com → certificato Let's Encrypt valido
- Schema DB: contacts, identities, events, messages, approvals, jobs
- Git init + primo commit. Claude Code 2.1.233 + CLAUDE.md + subagent guardrail-review
- Cantiere lead-gen host: raccolta Places API (New) operativa, sola lettura
  (`connectors/places.py`, `connectors/normalizza.py`,
  `scripts/cerca_places.py`, `tests/test_normalizza.py`). Il 30/08 raccolte
  2003 schede grezze da 5 celle (centro storico, Trastevere, Monti/Colosseo,
  Trevi/Spagna, Esquilino/Termini) con 128 chiamate API, salvate in
  `out/places/` sul VPS — non nel repo (`.gitignore`).
- Cantiere lead-gen host: resolver operativo (`scripts/risolvi.py`,
  migrazione `db/migrations/005_prospect.sql`). Gira dentro il container
  worker (`docker compose exec worker python -m scripts.risolvi`), non è un
  job — si lancia a mano, un file alla volta. Zero LLM, mai fusioni
  automatiche: chiavi forti (`google_places`/`dominio`/`telefono`) fondono,
  chiave debole (nome+indirizzo) solo segnala possibili doppioni, due
  contatti diversi su chiavi diverse restano un conflitto loggato.
  Idempotente: rilanciare lo stesso file due volte dà zero contatti nuovi
  (verificato anche a livello DB, zero identità duplicate).
  Numeri finali (30/08, 5 celle): **1197 contatti prospect**, 695 con
  telefono, 524 con sito proprio, 58 collegati a più di una struttura.
  **Regola del dominio contato**: un dominio genera identità solo se
  condiviso da al massimo `DOMINIO_MAX_STRUTTURE_CONDIVISE=8` place_id
  distinti nel batch (prima passata di conteggio in `risolvi.py`, prima
  della risoluzione); sopra la soglia vale come piattaforma non ancora
  riconosciuta — `sito_proprio=False`, nessuna identità, il link resta
  comunque nel payload. Serve perché una blocklist statica
  (`AGGREGATORI` in `connectors/normalizza.py`) non basta da sola: i booking
  engine e le OTA nuove spuntano di continuo, e senza il conteggio si
  scoprono solo quando hanno già fuso decine di strutture non correlate in
  un unico falso "gestore" (successo il 30/08 con krossbooking, spacest,
  vio, freecancellations, snaptrip, bluepillow, voyabay, trip.com — 8
  piattaforme mai viste prima, scoperte proprio così). A ogni run
  `risolvi.py` stampa i 10 domini più condivisi rimasti sotto soglia, per
  scovare il prossimo candidato senza doverlo cercare a mano.
- Cantiere lead-gen host: export punteggiato (`scripts/export_prospect.py`,
  gira dentro il container worker come `risolvi.py`) e skill di progetto
  `.claude/skills/leadgen-citta/SKILL.md` per ripetere l'intero processo su
  una nuova città senza ripensarlo. Punteggio deterministico (forma
  impresa 15, volume ospiti 0-25 in scala logaritmica, `n_strutture` a
  scala 2→20/3→30/4→40/5+→50, sito proprio 10, telefono 10) — ritarato il
  30/08 dopo aver misurato che con impresa=30 e bonus fisso i gestori con
  4-6 strutture finivano in posizione 48-112 su 1197, sotto singoli
  ostelli. CSV con `googleMapsUri` e colonna `esito` vuota da riempire a
  mano, in `out/export/` (non nel repo).
  Ogni contatto porta ora `attributi->>'citta'` (`--citta` obbligatorio in
  `risolvi.py`); i 1197 contatti esistenti backfillati a `'roma'`.

## In corso
- Cantiere lead-gen host: chiuso per Roma. Prossima città si apre solo se
  Narratours ha tour attivi lì — segue la skill `leadgen-citta`.
- Cantiere B (Firecrawl, ricerca email): dovrà filtrare su
  `attributi->>'sito_proprio'`, mai su `sito IS NOT NULL` — `sito` tiene il
  link grezzo anche quando è un aggregatore o una piattaforma di booking (è
  lì apposta, per non perdere il dato), quindi un filtro su `sito IS NOT
  NULL` manderebbe Firecrawl a raschiare pagine di booking.com/OTA invece
  che i siti veri delle strutture.

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
- **Email del depliant (29/08)**: `genera_poster`, dopo l'invio riuscito dei
  poster, accoda il job `invia_depliant` con `run_after = now() + interval
  '24 hours'` e `event_id` nel payload. Nuovo handler `invia_depliant`
  (one-shot, non self-chaining): legge email/nome/host_code dall'evento e
  manda un'email senza allegati dalla casella `REPLY_SMTP_*`
  (narratours.info@gmail.com, non quella dei poster — reputazione separata,
  messaggio leggero) con `connectors/mailer.invia_email_reply_box` (nuova
  funzione: stessa casella di `invia_risposta_email` ma senza quoting/
  In-Reply-To, è un messaggio nuovo non una risposta). Guardia di
  idempotenza standard su `messages`, ma `thread_id = f"{event_id}:depliant"`
  invece di `str(event_id)`: quel thread ha già una riga `out`/`email` per il
  poster, e l'indice unico è su `(thread_id, canale, direzione)` — con lo
  stesso thread_id la riga del depliant verrebbe scartata come "già inviata"
  senza mai partire. Notifica Telegram a invio riuscito. Testo in
  `connectors/testi.py`: `OGGETTO_DEPLIANT`/`CORPO_DEPLIANT`.

## Prossimi step (cantiere 1 — poster)
8. workflow GHL

## Cantiere 3 — DM Instagram/Facebook (avviato 26/08, connettore vero 27/08)
`POST /webhook/ghl/dm` in `backend/main.py` non è più ricognizione: scrive
evento `dm.received` + job `notifica_dm`. Campi affidabili (verificati con un
DM di prova il 26/08): `message_body`, `reply_channel`, `triggered_at` dentro
`customData`; `contact_id`, `email`, `first_name`, `last_name` alla radice.
- `message_body` vuoto/mancante → 200 + log INFO, nessun evento (notifiche di
  sistema di GHL, non messaggi veri).
- `reply_channel` è un **valore statico** scritto a mano nel workflow GHL
  (`"Instagram DM"` / `"Facebook messenger"`), non deriva dal canale reale del
  messaggio. Normalizzato per sottostringa case-insensitive
  (`_normalizza_canale_dm`); valore non riconosciuto → 200 + log WARNING
  (solo categoria, mai il valore grezzo), evento scartato.
  **Fragilità nota da costruzione**: se il filtro del workflow GHL cambia
  senza aggiornare la custom data statica, un DM Facebook potrebbe arrivare
  etichettato Instagram senza che nessuno se ne accorga.
- `triggered_at` (verificato su traffico reale il 27/08) **non** è né ISO
  8601 né epoch: fuso del sub-account GHL (Europe/Madrid), mese non
  zero-padded. Il parsing (`datetime.fromisoformat` + sostituzione `Z`)
  funzionava solo per caso e scartava eventi validi quando falliva — tolto.
  `scadenza` ora si calcola da `now()` al momento in cui il webhook arriva
  + 24h (finestra di risposta Meta), non più da `triggered_at`: la
  ricezione è un dato certo, il formato di `triggered_at` no.
  `triggered_at` resta nel payload dell'evento **grezzo, senza parsing** —
  dato diagnostico, utile in futuro per capire se GHL accumula ritardo, non
  per calcolare scadenze.
- **Non esiste un `conversation_id` né un id univoco di messaggio** nel
  payload GHL. `dedup_key = 'ghl-dm:' + contact_id + ':' + triggered_at`
  (valore **grezzo**, stringa non interpretata — serve solo a distinguere
  due messaggi, non a dire un'ora) per ora. Il webhook logga sempre a INFO
  tipo (e, se dict, campi) del campo
  `message` alla radice — potrebbe contenere qualcosa di più ricco di
  `message_body`, incluso un id di messaggio, ma va ancora osservato su
  traffico reale: **da rivedere la dedup_key** una volta letti quei log.
- Worker: handler `notifica_dm` (one-shot, non self-chaining). Guardia di
  idempotenza standard (`INSERT ... ON CONFLICT (thread_id, canale, direzione)
  ... DO NOTHING RETURNING id` su `messages`, direzione `in`). Notifica
  Telegram con marcatore canale (📷 IG / 💬 FB), mittente, countdown alla
  scadenza (riusa `riga_scadenza` — rinominata da `_riga_scadenza` perché ora
  condivisa tra `chiedi_approvazione` e questo handler) e anteprima testo
  troncata a 400 caratteri.
- Zero LLM. L'invio della risposta al DM non è in questo step: serve il
  `conversation_id` (assente nel payload) per rispondere via API — resta un
  passo a parte.
- **Invio collegato (27/08)**: `invia_risposta` ora dirama per
  `messages.canale` (letto tramite il JOIN già esistente con `events`, non
  serve `messages.contact_id` che resta NULL). Canale `instagram`/`facebook`
  → `connectors/ghl.invia_messaggio(contact_id, tipo, testo)`, con
  `contact_id` letto da `events.payload->>'contact_id'` e `tipo` mappato
  `instagram`→IG, `facebook`→FB. `conversationId`/`messageId` restituiti da
  GHL salvati nella nuova colonna `messages.payload` (JSONB,
  `db/migrations/004_messages_payload.sql`), per correlare i thread in
  futuro. Notifica Telegram di conferma dice "consegnata a GHL", non
  "inviata": il 200 di GHL significa solo "accettato", non conferma la
  consegna su Meta — non lo sappiamo ancora. Stessa guardia di scadenza
  (`approvals.scadenza`, già generica) e stessa guardia di idempotenza
  (`INSERT ... ON CONFLICT ... RETURNING id` su `messages`) usate per email.
  Canale non riconosciuto → `ValueError` (job failed + alert), mai un invio
  silenzioso. Il drafter DM (che dovrebbe creare le righe `approvals` per i
  DM in produzione) resta da scrivere — per ora il collaudo end-to-end passa
  dal nuovo handler manuale `test_approvazione_dm(contact_id, canale)`, che
  richiede un contatto GHL vero con la finestra ancora aperta.

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
- Guardia di idempotenza scritta prima dell'invio (email e DM): la riga in
  `messages` che marca "già inviato" viene committata PRIMA della chiamata
  SMTP/GHL. Se la chiamata fallisce dopo quel commit, un retry del job trova
  la riga già presente e non reinvia più. Trade-off scelto: mai un doppio
  invio, nel caso peggiore un messaggio registrato ma non partito davvero —
  da gestire a mano se capita, non risolto nel codice.
  Stesso trade-off, variante: in `genera_poster` l'INSERT del job
  `invia_depliant` avviene dopo che la guardia su `messages` per il poster è
  già stata scritta. Se il processo muore fra l'invio del poster e quel
  INSERT, un retry rilegge `gia_inviata=True` ed esce prima di riaccodare —
  il depliant non partirebbe mai. Non risolto, stessa categoria di rischio.
- Identity resolution mai implementata. Le tabelle contacts e identities
  esistono nello schema ma nessun flusso le popola: messages.contact_id è
  sempre NULL. Il §5.1 del contesto la elenca tra le tre cose da progettare
  bene subito, perché ritrofittarla è doloroso. Oggi non blocca nulla — ogni
  canale lavora isolato — ma appena lo stesso prospect scriverà via email e
  via DM, non avremo modo di sapere che è la stessa persona.

## DATI MANCANTI
- poster_con_codice.png (stesse dimensioni, con codice esempio) — solo per confronto
  visivo, non serve alla generazione

## Note operative
- DNS: narratour-review.com → zona su HOSTINGER
        narra-tours.com     → zona su CLOUDFLARE
- Segreti in /root/argo/.env (mai committato)

## Backup (27/08)
`backup/dump.sh` (cron giornaliero alle 3:00, già esistente) ora chiama in
coda `backup/invia_backup.py`: spedisce l'ultimo dump via email
all'operatore (`BACKUP_EMAIL_DEST`), allegato + conteggio righe delle
tabelle principali nel corpo. Sopra i 15MB non tenta l'invio (margine sotto
il limite allegati di Gmail) e alerta via Telegram invece; alert Telegram
anche se non trova nessun dump o se l'invio fallisce. Email operativa verso
l'operatore: non scritta in `messages` (eccezione documentata in
CLAUDE.md — quella tabella traccia le conversazioni con host/prospect, non
il traffico interno). Testato end-to-end il 27/08, email arrivata
correttamente.

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
