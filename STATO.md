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
  Il 31/08, prima dell'azzeramento mensile del tier gratuito, aggiunte 6
  celle (testaccio_aventino, prati_borgo, san_giovanni, salario_nomentano,
  flaminio_parioli, san_lorenzo_pigneto) senza dry-run, una alla volta: altre
  94 chiamate (14+39+21+6+6+8), nessuna ha esaurito il proprio tetto di 120.
  11 celle totali, ~222 chiamate cumulative nel mese. Un sotto-quadrante
  (`prati_borgo#q0#q3`) resta saturo anche al livello massimo di bisezione —
  area densa non coperta per intero, da rivedere a mano se conta davvero
  (segnalato da `cerca_places.py`, non un errore).
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
  Aggiornati (31/08, 11 celle): **1998 contatti prospect**, 1388 con
  telefono, 995 con sito proprio, 135 collegati a più di una struttura.
  Idempotenza riverificata sull'ultimo file delle 6 celle nuove (0 contatti
  nuovi, 0 identità al rilancio).
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
- **Cantiere lead-gen host — cantiere B (email), chiuso (31/08)**:
  `connectors/fetch.py` (GET diretto stdlib, un tentativo, timeout 10s,
  motivo del fallimento classificato in timeout/dns/403/404/500/altro) +
  `scripts/estrai_email.py` (home + eventuale pagina contatti, regex
  deterministica in `connectors/normalizza.py`, zero LLM). Filtra su
  `attributi->>'sito_proprio' = 'true'`, mai su `sito IS NOT NULL`. Il
  campione di misura da 30 (18 con email, errori sparsi per motivo senza
  concentrazione) ha mostrato che Firecrawl non serve — non aperto.
  Lanciato su tutti i 524 prospect a lotti da 100 (`--tutti --offset`) con
  scrittura reale (`--scrivi`): email in `contacts.email` solo se vuoto,
  identità `('email', indirizzo)` in `identities` (`ON CONFLICT DO
  NOTHING`), `attributi.email_altre`/`email_personale` (dominio email ≠
  dominio sito, nessuna whitelist di provider) sempre aggiornati.
  **Blocklist placeholder (1/09), da lista fissa a regola generale**: dopo
  due giri in cui spuntavano varianti sempre nuove (prima `mail.com`/
  `company.co`/`test.com`/`domain.com`/`yourdomain.com`, poi `example.com`/
  `dominio.com`/`email.com`/`esempio.it`/`mysite.com`), la blocklist di
  `connectors/normalizza.py` scarta ora anche chiunque contenga una
  `PAROLA_SEGNAPOSTO` (example, esempio, mysite, dominio, tuodominio,
  yourdomain, tuosito, email.com, indirizzo, utente, nomeazienda) come
  sottostringa nel local-part O nel dominio — non serve più inseguire ogni
  nuova variante una alla volta. Restano a lista fissa/uguaglianza esatta
  solo `noreply`/`no-reply`/`postmaster`/`webmaster`/`privacy` (local-part),
  `wordpress`/`sentry` (sottostringa dominio) e `mail.com`/`company.co`/
  `test.com`/`domain.com` (uguaglianza esatta dominio — nomi che non
  contengono nessuna parola segnaposto). Eccezione: "dominio" è sottostringa
  di "condominio" (amministratori di condominio reali, es.
  `info@condominiorossi.it`) — `_contiene_segnaposto()` la esclude
  esplicitamente, unica parola della lista con questo problema.
  Ogni run stampa anche i 15 domini
  email più frequenti tra le scelte: un placeholder si vede da solo perché
  compare su decine di siti scollegati (verificato dopo la correzione:
  nessuna concentrazione sospetta, solo provider reali — gmail 152,
  libero.it 10, hotmail.com 6, ...).
  Ad ogni scoperta di placeholder, i contatti già scritti sono stati
  svuotati (`contacts.email`, `attributi.email_altre/email_personale`,
  identità collegata) e ri-estratti: 4 la prima volta (2 recuperati, 2
  rimasti vuoti), 8 la seconda (6 recuperati, 2 rimasti vuoti — i siti non
  avevano altra email valida).
  Numeri finali (1/09, 995 prospect idonei): **598 con email, 343 su
  dominio proprio, 255 personali** (gmail/libero/hotmail/...).
- **Cantiere lead-gen host — estrazione social, chiusa (1/09)**: profilo
  Instagram e pagina Facebook per i prospect senza sito proprio raggiungibile
  via email, per l'outreach manuale di settembre. Due fonti a costo zero,
  `scripts/estrai_social.py` (`--tutti --offset`, come `estrai_email.py`):
  1) contatti con `sito_proprio` falso il cui `sito` grezzo è già un link
  Facebook/Instagram, parsing diretto senza rete; 2) contatti con
  `sito_proprio` vero, home + eventuale pagina contatti scaricate con
  `connectors/fetch.py`, primo profilo trovato negli `<a href>`.
  Refactor: `con_schema()`/`host_di()`/`estrai_link()`/`trova_link_contatti()`
  spostate da `estrai_email.py` a `connectors/fetch.py` (secondo uso reale
  della stessa logica), `estrai_email.py` ora le importa. Nuovo
  `tests/test_fetch.py`.
  Normalizzazione in `connectors/normalizza.py`
  (`normalizza_instagram`/`normalizza_facebook`): tengono solo i profili,
  scartano post/reel/storie/condivisioni/plugin
  (`IG_RISERVATI`/`FB_RISERVATI`); eccezione `profile.php?id=...` (unico
  identificatore per pagine senza nome vanity, tenuto anche se la regola
  generale è "niente query"); schemi multi-segmento `pages/Nome/id` e
  `people/Nome/id` preservati per intero, ma solo con l'id (terzo segmento)
  presente — senza, scartato: il solo primo segmento perderebbe
  l'identificativo (bug reale trovato a campione: 11+5 contatti con
  `facebook.com/pages`/`facebook.com/people` tronchi, corretti e
  ri-estratti), e `facebook.com/pages/category/hotel` (directory categorie
  di Facebook, non una pagina — altro bug reale, "category" esplicitamente
  escluso) sarebbe stato tenuto come se "category" fosse il nome pagina.
  Handle Instagram validato contro il charset vero
  (lettere/cifre/punto/underscore) per scartare href rotti tipo
  `instagram.com/https://instagram.com/handle`.
  `BUILDER_SOCIAL_DA_SCARTARE`: account di default lasciati da page
  builder/hosting mai configurati dal gestore (wix, wixstudio, shopify,
  squarespace, webador, weebly, wordpress, godaddy, jimdo, altervista,
  aruba, ionos) — scoperti a campione, scartati sia per Instagram sia per
  Facebook. Ogni run stampa i 15 handle/pagine più frequenti, stessa logica
  del top-15 domini email, per far emergere da soli i prossimi builder non
  ancora in lista.
  `attributi.instagram` (handle nudo) e `attributi.facebook` (URL
  normalizzato) sono sovrascrivibili — dati derivati, non un valore storico
  da proteggere come l'email — ma scritti solo quando il run trova
  qualcosa, per non cancellare un valore buono di un run precedente.
  Due colonne aggiunte a `export_prospect.py`.
  **`facebook.com/1278` indagato e risolto (1/09)**: href letterale
  identico (`<div class="socialHubWrapper"> <a href="https://facebook.com/1278" ...
  dm_dont_rewrite_url="true">`) su 9 siti indipendenti — widget social di
  un booking engine condiviso (diversi domini `*.icalu.com` tra i 9)
  mai configurato, non una pagina reale. Non serviva un'altra entry in
  `BUILDER_SOCIAL_DA_SCARTARE` (non si conosce il nome del builder): regola
  generale in `normalizza_facebook()` invece — uno slug puramente numerico
  come `facebook.com/<cifre>` è scartato sempre, perché i veri id numerici
  Facebook sono lunghi 15-17 cifre e compaiono solo dentro
  `profile.php?id=`/`pages/.../<id>`/`people/.../<id>`, mai come slug
  diretto. I 9 contatti svuotati e ri-estratti: nessuno aveva un'altra
  pagina Facebook reale sul sito.
  **Numeri finali (1/09, 1416 prospect con sito): 237 con Instagram, 289
  con Facebook, 346 con almeno uno dei due, 6 raggiungibili solo via
  social** (nessuna email né telefono).
- **Cantiere lead-gen host — Roma chiuso (1/09), stato finale**: **1998
  contatti prospect**, **1388 con telefono**, **598 con email** (343 su
  dominio proprio, 255 personali), **346 con almeno un profilo social**
  (Instagram/Facebook), **6 raggiungibili solo via social** (nessuna email
  né telefono). Dettagli, decisioni e bug corretti lungo il percorso nei
  punti sopra; skill `leadgen-citta` aggiornata con tutti i passi (celle →
  resolver → export → email → social) per ripetere il processo su una
  città nuova.
- **`scripts/export_instantly.py` (1/09)**: export ripetibile per le
  ondate della campagna Instantly, sostituisce lo script ad hoc del primo
  giro. Sola lettura (contatti + `soppressioni`), nessuna scrittura.
  Selezione: `stato='prospect'`, email non vuota, `email_personale` falso
  (disattivabile con `--includi-personali`, per un uso futuro), esclusi
  quelli in `soppressioni` e quelli nei CSV passati a `--escludi`
  (ripetibile — così l'ondata 2 non ripesca i lead dell'ondata 1), ordinati
  per punteggio decrescente (`calcola_punteggio` riusata da
  `export_prospect.py`), tagliati a `--limite` (default 50). File scritto:
  `instantly_ondata<N>.csv` (`--ondata`, default 1) — sovrascritto se
  rilanciato con lo stesso N, è un deliverable rigenerabile.
  Oltre alle colonne dati (email, struttura, citta, tipo, n_strutture,
  telefono, sito, punteggio, `Nome Business` = duplicato di struttura per
  il mapping variabili di Instantly), tre colonne di copy — `codice_host`,
  `zona`, `chiusura` — **non derivate dal contatto**: `zona` è un esempio
  di copertura del servizio citato nel testo, non la zona geografica vera
  del contatto. Tutte e tre sono rotazioni stabili su un pool costante via
  hash SHA-256 dell'id (`hashlib`, non `hash()` di Python che è salato per
  processo): stesso contatto, stesso valore in ogni export futuro, finché
  `POOL_CODICI`/`POOL_ZONE`/`POOL_CHIUSURE` non cambiano ordine/contenuto —
  da non editare una volta in uso, solo estendere in coda. A fine run
  stampa la distribuzione per zona (verifica, non un fallback: l'assegnazione
  non fallisce mai).
  `instantly_ondata1.csv` rigenerato nel nuovo formato: 50 righe su 343
  idonei (dominio proprio, nessuno ancora in `soppressioni`, che è vuota).

## In corso
- 30 telefonate ai contatti multi-struttura.
- Prima campagna Instantly da 50 lead sui contatti con email su dominio
  proprio (`instantly_ondata1.csv`).

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
- **Caselle in lettura (2/09)**: attive le cinque caselle `landmarkpixel.com`
  più `narratours.info@gmail.com`, tutte su `imap.gmail.com` con password
  per le app. Le due caselle `.click` sono state tolte dalla lettura finché
  restano in warmup — da rimettere tra un mese. Quando succederà servirà un
  host IMAP per singola casella (oggi `IMAP_HOST` è un'unica variabile
  globale in `imap_reader.py`, usata per tutte le caselle): le `.click`
  torneranno su Hostinger, mentre le altre restano su Google.
  `WARMUP_TAG` è ora `rule-once`.
  **Due difetti noti, da affrontare nel cantiere risposte**:
  1. il filtro warmup guarda solo l'oggetto (`WARMUP_TAG.lower() in
     oggetto.lower()` in `leggi_nuove()`) e quindi lascia passare i
     rimbalzi (bounce) come messaggi veri;
  2. le email automatiche di Google (`no-reply@google.com`, avvisi di
     sicurezza) generano notifiche inutili — non sono conversazioni con
     host/prospect.
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
- Filtro warmup lascia passare i rimbalzi: `leggi_nuove()` classifica come
  warmup solo controllando se `WARMUP_TAG` compare nell'oggetto — un
  rimbalzo (bounce) non ha il tag nell'oggetto e passa come email vera. Da
  affrontare nel cantiere risposte, non risolto qui.
- Email automatiche di Google generano notifiche inutili: `no-reply@google.com`
  e gli avvisi di sicurezza vengono letti come email vere e notificati su
  Telegram. Da affrontare nel cantiere risposte, non risolto qui.
- Le caselle `.click` (in warmup) richiederanno un host IMAP per casella
  quando rientrano in lettura tra un mese: torneranno su Hostinger mentre
  le altre restano su Google, e oggi `IMAP_HOST` è un'unica variabile
  globale in `imap_reader.py`, condivisa da tutte le caselle.

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
