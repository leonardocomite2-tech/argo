# STATO — aggiornare a fine di ogni step

## CANTIERI

Blocco strutturato per `cantieri_aperti()` (`argo/stato.py`). Una riga per
cantiere, vocabolario fisso: `Stato` ∈ {aperto, in attesa, chiuso, da
confermare}; `Aspetta` ∈ {Leonardo, il sistema, terzi, calendario, —, da
confermare}. Aggiornare insieme alla nota di sessione (vedi CLAUDE.md).

| Nome | Stato | Aperto il | Aspetta | Sessione più recente |
|---|---|---|---|---|
| Cantiere 1 — poster | in attesa | da confermare | Leonardo | 18/08/2026 — nessuna intestazione `## ` dedicata; resta solo l'item 8 "workflow GHL" |
| Cantiere 2 — email | aperto | da confermare | il sistema | 03/09/2026 — nessuna intestazione `## ` dedicata; "cantiere risposte, secondo pezzo" (classificazione+bozze); dichiarato cantiere attivo in CLAUDE.md |
| Cantiere 3 — DM Instagram/Facebook | in attesa | 26/08/2026 | Leonardo | 27/08/2026 — invio collegato; drafter DM non scritto |
| Lead-gen host (Roma) | chiuso | da confermare | — | 01/09/2026 — "Roma chiuso", stato finale |
| Panoptes — Mappa | in attesa | 09/09/2026 | calendario | Sessione 10/9/2026, passo 4 — test accettazione esito pieno; chiusura prevista 17/09/2026 |
| Designer (bonifica yourservice-it) | in attesa | da confermare | Leonardo | Sessione 2026-09-11 (continua) — Fase C, via libera Ipotesi 1; in attesa che Leonardo reincolli i blocchi |
| Argo — la voce | aperto | 10/09/2026 | Leonardo | Sessione 2026-09-11 — passo 4 + correzioni: anti-invenzione, brevità, costo (7.787 token/chiamata) — in attesa del giudizio di Leonardo sul carattere, nulla committato |
| Regista Sonora v10 | da confermare | da confermare | da confermare | n/d — fuori repo, citato solo come motivo di deroga |

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

## Dettaglio implementativo (poster step 5-7 e cantiere 2 — email)

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
- **Cantiere risposte, primo pezzo (3/09) — filtri email in ingresso**:
  i due difetti noti sopra sono risolti. `connectors/imap_reader.py`
  classifica ogni messaggio con `classifica_messaggio(msg, WARMUP_TAGS)`,
  in ordine fisso: warmup → rimbalzi → automatiche → amministrazione
  Google. `WARMUP_TAG` ora accetta più valori separati da virgola
  (`_parse_warmup_tags`), e il tag si cerca nel testo grezzo completo del
  messaggio (`msg.as_string()`: intestazioni + corpo + parti annidate),
  non solo nell'oggetto — copre il caso dei rimbalzi di warmup, dove il
  tag è nel messaggio originale allegato (`message/rfc822` dentro il
  `multipart/report`). Rimbalzi riconosciuti da mittente
  (`MAILER-DAEMON`/`postmaster@`) o da `Content-Type: multipart/report;
  report-type=delivery-status`; indirizzo fallito e codice estratti dalla
  sotto-parte `message/delivery-status`. Codice `5.x.x` → definitivo,
  `4.x.x` (o non estraibile — default prudente) → temporaneo. Amministrazione
  Google riconosciuta **solo dal mittente** (dominio `google.com`/
  `googlemail.com`, anche sottodomini come `accounts.google.com`, local-part
  che inizia per `no-reply`/`noreply`), mai dall'oggetto — confermato con
  oggetti reali dai log ("Tips for using your new inbox" non è un avviso di
  sicurezza ma va comunque ignorato). Il controllo "automatiche" esclude i
  domini Google dal proprio check sul prefisso no-reply/noreply, altrimenti
  finirebbero sempre lì (essendo prima nell'ordine) e la categoria
  `google_admin` non scatterebbe mai.
  `leggi_nuove()` non filtra più nulla: restituisce tutti i messaggi
  annotati con `motivo_scarto`. La decisione si sposta nell'handler
  `leggi_email` (`worker/loop.py`): se `motivo_scarto` è `None` comportamento
  invariato (evento `email.reply` + job `notifica_risposta`); altrimenti
  evento `email.filtrata` con `payload.motivo` (e `indirizzo_fallito`/
  `codice_rimbalzo` per i rimbalzi), nessun job di notifica — mai scartato
  in silenzio. Rimbalzo definitivo con indirizzo estratto → riga in
  `soppressioni` (`tipo='email', motivo='bounce'`, schema già pronto,
  nessuna migrazione). Log di fine giro: quanti messaggi passati e quanti
  filtrati per motivo. Digest serale (`componi_digest_serale`): due nuove
  sezioni, conteggio filtrati per motivo (24h) e indirizzi finiti in
  `soppressioni` per bounce (24h, troncati a 5 con "e altri N" come le
  altre sezioni — riepilogo, non un rimbalzo alla volta). Test in
  `tests/test_filtri_email.py` (stile CASI, un caso per categoria, incluso
  un rimbalzo vero con il tag warmup nel messaggio allegato).
  Trade-off noto: un rimbalzo senza `message/delivery-status` parsabile è
  trattato come temporaneo anche se fosse definitivo (senza indirizzo
  comunque non c'è nulla da sopprimere — impatta solo il conteggio nel
  digest). La classificazione LLM e la stesura di bozze restano il
  prossimo pezzo del cantiere.
  **Incidente e fix (3/09, scoperto prima del deploy del secondo pezzo)**:
  un'email di warmup di una nuova ondata (mittente
  `paige.m@leadifylabs.org`, oggetto "How can we help you? | Q086N4B
  ZWNVS42") è passata come risposta vera perché il token non era in
  `WARMUP_TAG` (conteneva solo `rule-once`) — sarebbe costata una chiamata
  al modello una volta collegato il classificatore. `WARMUP_TAG` ora è
  `rule-once,ZWNVS42,HX9J9MY`, ma soprattutto è stata aggiunta una regola
  **strutturale**, indipendente dal token: un oggetto la cui riga `Subject:`
  termina con una pipe seguita da uno o due gruppi alfanumerici maiuscoli di
  6-10 caratteri (`_e_pattern_warmup_soggetto` in `connectors/imap_reader.py`)
  è trattato come warmup a prescindere dal token esatto — i token cambiano
  ad ogni ondata, la struttura no. Controlla anche l'oggetto annidato di un
  eventuale rimbalzo, come già fa il controllo sui token letterali. Trade-off
  accettato: un oggetto reale (non di warmup) che terminasse per coincidenza
  con "| XXXXXX" verrebbe scartato per errore — rischio ritenuto trascurabile,
  non osservato su traffico reale. Test aggiunti in
  `tests/test_filtri_email.py`: il caso reale di Paige (bloccante solo dalla
  regola strutturale, `WARMUP_TAG` di test non contiene quel token) e un
  oggetto con token misto (tag letterale + nuovo formato).
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
- **Cantiere risposte, secondo pezzo (3/09) — classificazione LLM + bozze,
  collegate al traffico vero**: prima chiamata a un modello in produzione in
  questo repo.
  - `connectors/llm.py`: connector sottile (stile `places.py`, solo stdlib),
    `chiama(system, prompt, max_tokens, temperature)` POST a
    `https://api.anthropic.com/v1/messages`, modello `claude-haiku-4-5-20251001`.
    Retry solo su errori di rete e 5xx (niente 429, a differenza di
    `places.py`), 3 tentativi. Logga sempre token in ingresso/uscita e
    latenza. Tetto giornaliero `LLM_TETTO_GIORNALIERO` (env, oggi 150):
    contatore **in-memory** nel processo worker — vedi DECISIONI APERTE per
    il trade-off. Al superamento: notifica Telegram una sola volta al giorno
    e solleva `TettoLLMRaggiunto` prima di qualunque chiamata HTTP.
  - `brain/classifier.py`: `classifica(mittente, oggetto, testo)`, enum
    chiuso (`interessato, domanda, obiezione, prezzo_o_contratto,
    non_interessato, disiscrizione, fuori_tema`), temperatura 0, JSON
    forzato. `prezzo_o_contratto` è per le condizioni del *proprio*
    contratto/commissione come host (da negoziare), non i prezzi dei tour
    per l'ospite (quelli sono `domanda`, coperti da `knowledge/conoscenza.md`).
    JSON non valido o categoria fuori enum → `ClassificazioneErrore`, motivo
    sempre categorico (mai il testo grezzo del modello nell'alert). Eval in
    `tests/eval_classificatore.py`, 21 casi scritti a mano (uno o più per
    categoria, casi di confine inclusi), chiamate reali all'API, rilanciabile
    dopo ogni modifica al prompt — 21/21 passati alla prima stesura.
  - `brain/drafter.py`: `redigi_bozza(mittente, oggetto, testo, categoria)`,
    legge `knowledge/conoscenza.md` ad ogni chiamata (niente cache, il file
    può essere aggiornato senza riavviare il worker). Se la domanda esce dal
    perimetro della base di conoscenza, il drafter stesso lo dichiara
    (`puo_rispondere: false` + motivo) invece di inventare — verificato a
    mano su un caso reale (punto di partenza di un tour, dato mancante in
    `conoscenza.md`: risposta corretta "verifico e rispondo a breve").
    **Fix tono (3/09), due giri**: il primo collaudo su un caso realistico ha
    mostrato prima lei/tu mescolati ("Appendi i poster... ai tuoi ospiti" +
    "risponda pure"), poi lei/voi mescolati ("il vostro B&B", "rispondete
    pure"). Il prompt ora è esplicito su entrambe le forme sbagliate e sui
    possessivi riferiti a QUALSIASI sostantivo (non solo "ospiti" — "il suo
    B&B", non "il vostro B&B"), non solo "dare del lei" in generale.
    Temperatura abbassata a 0 (come il classificatore): niente creatività
    richiesta per risposte brevi da una base di conoscenza fissa, e la
    determinatezza rende ripetibile il collaudo di un fix di prompt.
    **Osservazione (non un bug da correggere)**: durante il collaudo il
    drafter ha una volta contato male i caratteri di un codice sconto di
    esempio (10 lettere, dichiarate 11) rifiutandolo per errore — un limite
    noto dei modelli linguistici sul conteggio esatto di caratteri. Non
    richiede un fix di codice: è esattamente il motivo per cui ogni bozza
    passa da un'approvazione umana prima di partire, mai in automatico.
  - `worker/loop.py`: nuovo helper `_valuta_e_rispondi()`, chiamato da
    `notifica_risposta` e `notifica_dm` dopo la guardia di idempotenza su
    `messages` (che ora cattura anche l'id della riga inserita). Diramazione
    per categoria: `interessato`/`domanda` con confidenza > 0.7 → bozza dal
    drafter → `INSERT INTO approvals` + `chiedi_approvazione()` (stessa
    identica catena di `test_approvazione`/`test_approvazione_dm`, mai un
    invio diretto); `obiezione`, `prezzo_o_contratto`, `fuori_tema` o
    confidenza ≤ 0.7 → solo notifica con contesto, nessuna bozza;
    `non_interessato`/`disiscrizione` → riga in `soppressioni` (sempre) +
    `UPDATE contacts SET stato='non_interessato'` con match best-effort
    (`email` per le email, `ghl_contact_id` per i DM, nessuna creazione — non
    esiste identity resolution). Se il contatto non viene trovato: **non è un
    no-op silenzioso** — `messages.payload.contatto_trovato=false`, nota
    esplicita nella notifica immediata, e nuovo conteggio nel digest serale
    ("N disiscrizioni/non_interessato senza contatto corrispondente" nelle
    24h) — un mancato match è un segnale (lead da un'altra fonte, o email
    diversa da quella in anagrafica), non un caso normale da ignorare.
    `messages.categoria`/`messages.confidence` (colonne orfane dallo schema
    iniziale) ora sono scritte per ogni messaggio classificato.
  - **Invio email ora dalla casella originaria, non più dalla reply-box
    fissa**: `invia_risposta` (ramo email) legge anche
    `e.payload->>'destinatario'` e risolve la password app con il nuovo
    `connectors.imap_reader.password_per(user)`. `invia_risposta_email()` in
    `connectors/mailer.py` è ora parametrica su `mittente_user`/
    `mittente_pass` invece di usare sempre `REPLY_SMTP_*`. `Reply-To` resta
    fisso su `REPLY_SMTP_USER` (narratours.info@gmail.com), così le risposte
    dell'host convergono sempre lì anche se il primo giro è partito da una
    delle caselle `landmarkpixel.com`.
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
- Tetto giornaliero di chiamate LLM (`LLM_TETTO_GIORNALIERO`, oggi 150) tenuto
  in un contatore in-memory nel processo worker (`connectors/llm.py`), non su
  DB. Trade-off scelto: connector resta sottile (zero dipendenza DB, come
  `places.py`), ma il contatore si azzera ad ogni riavvio del worker (raro,
  solo su deploy) — nel caso peggiore il tetto reale del giorno è più alto di
  150 se il worker riavvia più volte. Non risolto nel codice.
- Classificazione/bozza fallita (`ClassificazioneErrore`/`DrafterErrore`, es.
  JSON non valido dal modello) non viene ritentata a livello di job: la
  guardia di idempotenza su `messages` (scritta prima della classificazione)
  fa sì che un retry del job veda il messaggio "già notificato" e esca subito
  senza mai richiamare l'LLM. Trade-off scelto: un errore di classificazione
  è terminale per quel messaggio — arriva solo la notifica Telegram, nessun
  retry automatico, gestione a mano se capita.
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
- **Risolto (3/09)** — Filtro warmup lasciava passare i rimbalzi ed email
  automatiche di Google generavano notifiche inutili: vedi cantiere
  risposte, primo pezzo, sopra. Trade-off rimasto: un rimbalzo senza
  `message/delivery-status` parsabile è trattato come temporaneo anche se
  fosse definitivo — nessun indirizzo estratto, quindi nessuna soppressione
  mancata, solo un conteggio impreciso nel digest.
- Le caselle `.click` (in warmup) richiederanno un host IMAP per casella
  quando rientrano in lettura tra un mese: torneranno su Hostinger mentre
  le altre restano su Google, e oggi `IMAP_HOST` è un'unica variabile
  globale in `imap_reader.py`, condivisa da tutte le caselle.
- **RE02 (mappa Panoptes)** — nessuna consultazione di `soppressioni` in
  `invia_risposta` prima dell'invio: una risposta approvata può partire
  verso un indirizzo finito in `soppressioni` dopo l'approvazione, incluso
  un disiscritto. L'igiene minima del PIANO_OPERATIVO richiede
  `soppressioni` consultata prima di ogni invio. Backlog del cantiere
  email, non di Panoptes.
- **Gate Telegram — rollback compensativo di `in_modifica` senza rete
  (emerso 10/9/2026, non in mappa).** Il ramo `modif` di
  `_gestisci_callback_telegram` (`backend/main.py:330-377`) claima lo stato
  `in_modifica`, poi chiama `chiedi_testo_corretto` (invio Telegram
  esterno); se fallisce, un blocco `except` riporta lo stato a `in_attesa`.
  Se quel rollback stesso non viene eseguito (processo ucciso tra le due
  istruzioni, eccezione fuori dal blocco coperto) l'approvazione resta
  bloccata in `in_modifica` per sempre: l'unico altro ramo che ne esce è
  `_gestisci_modifica_telegram`, che matcha su `tg_message_id` — se quel
  campo non è mai stato scritto, non c'è più modo di uscirne. Nessun
  controllo periodico di `manutenzione_sistema` guarda lo stato
  `in_modifica`, quindi il blocco è silenzioso: nessun alert, nessun log
  ricorrente. Candidato a contratto (`garantito_da: nessuno`) da valutare
  nel cantiere email: un controllo periodico che segnali `in_modifica`
  fermo oltre una soglia.
- **Gate Telegram — ramo di decisione senza `_accoda_invia_risposta`
  (emerso 10/9/2026, non in mappa).** Le quattro transizioni di stato in
  `backend/main.py` (appr, rifiu, modif→modificata via reply) chiamano
  tutte `_accoda_invia_risposta` dopo l'`UPDATE`. Non c'è oggi un caso reale
  in cui manchi, ma non c'è nemmeno una garanzia strutturale che leghi le
  due cose: un ramo nuovo, o una modifica a uno esistente, che decida lo
  stato senza accodare il job lascia l'approvazione `approvata`/`modificata`
  ma mai eseguita — in silenzio, senza errore né alert, scopribile solo
  guardando a mano la tabella `approvals`. Candidato a contratto
  (`garantito_da: nessuno`) da valutare nel cantiere email: un controllo
  periodico che confronti approvazioni decise senza job `invia_risposta`
  corrispondente.
- **`verifica_mappa.py` (passo 4, 10/9/2026) — limite residuo su env
  annidato.** Per evitare falsi positivi sull'env, lo script esclude dallo
  scope di una pipeline le voci `codice` che coincidono ESATTAMENTE con
  una voce di un condiviso che usa (caso reale: `worker/loop.py:1210-1388`
  dichiarato identico da `risposte_email`/`dm_instagram_facebook` e da
  `invia_risposta`). Non copre l'annidamento parziale (`alert_una_volta`
  749-764 dentro `manutenzione_sistema` 749-913): oggi innocuo perché
  `alert_una_volta.env` è vuoto, ma se in futuro guadagnasse una env
  darebbe un falso positivo su `manutenzione_sistema`. Falso positivo
  tollerabile per policy (mai falso negativo), ma da tenere a mente.
- **(risolto 10/9/2026, poi rivisto 11/9/2026) Cantiere Designer, h1 doppio
  yourservice-it — criterio del pavimento corretto, non la pagina; il fix
  al markup era superfluo.** `.nt-p1-hero`/`#ntHero` coesistevano sempre
  nel DOM. Fase B: `pavimento.mjs` misurava h1:2 perché contava i nodi
  grezzi del DOM invece dell'albero di accessibilità — due h1 nel sorgente
  sono validi HTML5 finché uno solo è esposto. Corretto lo script (conta
  gli h1 esposti, non nascosti da `display:none`/`visibility:hidden`/
  `[hidden]`/`aria-hidden`, §9 di `modalita/narratours.md`) — criterio
  giusto, resta. Ma Fase B aveva ANCHE aggiunto `display:none` reciproco a
  861px nei blocchi, soglia indovinata (mai misurata sul builder): Fase C
  ha misurato sulla live intatta che GHL già nascondeva le due hero da
  solo con un `display:none` di piattaforma reale (confine 767/768px, non
  861) — il problema non esisteva sulla pagina reale, solo nella
  ricomposizione locale senza quel CSS. Il fix 861px è stato **rimosso**
  (era la causa di una finestra morta vera, vedi bullet sotto): i blocchi
  sono tornati identici all'originale pre-bonifica su questo punto
  (`git diff 771185a` vuoto). La duplicazione fisica del markup
  desktop/mobile resta come debito separato, vedi bullet sotto.
- **Cantiere Designer, duplicazione desktop/mobile del markup
  (10/9/2026).** Causa comune a tre sintomi su `yourservice-it`: markup
  desktop e mobile duplicati, mai rimossi dal DOM (solo nascosti per
  viewport). H1 doppio (sopra, chiuso lato criterio pavimento, non lato
  struttura); 6 iframe Vimeo su 3 video distinti duplicati desktop+mobile
  (non 7 come nell'orientamento del cantiere); 2 iframe form GHL con lo
  stesso id duplicati. Rimedio comune: unificare in un markup responsive
  unico — candidato principale del prossimo intervento, non di questa Fase
  B. Dettagli in `modalita/narratours.md` §8.
- **Cantiere Designer, oro come testo su sfondo chiaro (10/9/2026) — debito
  di brand, non di bonifica.** `#c49a3c` su crema/bianco è 2,48–2,61:1
  (WCAG richiede 4,5, o 3 per testo grande — non lo raggiunge nemmeno
  quello). È un colore di brand (`NarraTours_Modello_Business.md`) usato su
  tutto il sito: non corretto solo su `yourservice-it` per non creare
  incoerenza tra pagine. Tre opzioni con rapporti calcolati in
  `modalita/narratours.md` §8, nessuna scelta.
- **Cantiere Designer, footer confermato globale — fix nel repo, non
  incollato (10/9/2026).** `blocco_header.html`/`blocco_footer.html` sono
  Header/Footer Tracking, condivisi a livello sito (confermato da Leonardo
  nel commento dei file, corroborato da baseline: stesso `document.title`
  su tutte e 6 le pagine). Il fix di contrasto footer resta committato ma
  non va incollato nella pagina di prova Fase C — tocca tutte le pagine
  live insieme, serve una decisione a parte. Rapporti in
  `modalita/narratours.md` §8.
- **(risolto 11/9/2026) Cantiere Designer, RISCHIO — noindex pagina di
  prova.** La regola era sbagliata, non solo contraddetta: annullata.
  Sostituita in `modalita/narratours.md` §2 regola 4 con "le pagine di
  prova non si pubblicano; la verifica avviene su `/preview/`, che serve
  la versione salvata — nessun noindex necessario". Verificato in Fase C:
  la pagina di prova (duplicata da `yourservice-it`, mai pubblicata) è
  raggiungibile solo da chi ha l'URL `/preview/<pageId>`.
- **(risolto 11/9/2026) Cantiere Designer, RISCHIO — finestra morta
  768-860px sull'anteprima GHL, Fase C test N.2.** Causa isolata: due
  meccanismi di visibilità indipendenti che non si allineavano — GHL
  nascondeva l'hero mobile da un suo `display:none` di piattaforma a
  partire da 768px (confine reale, misurato sulla live intatta), mentre il
  fix Fase B nascondeva l'hero desktop sotto 861px (soglia indovinata, non
  misurata sul builder). Misurato sulla live: nessuna finestra morta
  esiste lì, GHL gestisce già da solo la visibilità correttamente a ogni
  larghezza (375-1024px testate). **Decisione di Leonardo: IPOTESI 1 — il
  fix Fase B era superfluo ed era la causa del bug.** Rimosso da
  `blocco_01.html`/`blocco_hero_mobile_v3.html`. Test anti-finestra-morta
  ripetuto sulla ricomposizione locale (con `css_piattaforma_ghl.html`,
  riproduzione delle classi GHL misurate, aggiunto a `costruisci.py` per
  fedeltà) a 375/767/768/800/830/860/861/900/1024px: PASS, esattamente una
  hero a ogni larghezza, stesso esito della live. `baseline_narratours.md`
  e `modalita/narratours.md` corrette: l'"h1: 2" originale era un falso
  positivo del criterio vecchio, non un bug delle pagine — vedi bullet
  sopra e dettagli nella sessione sotto. **Resta da fare**: Leonardo
  reincolla i blocchi corretti sulla pagina di prova, poi si ripete
  pavimento + anti-finestra-morta sull'anteprima reale (non solo locale).

## DATI MANCANTI
- poster_con_codice.png (stesse dimensioni, con codice esempio) — solo per confronto
  visivo, non serve alla generazione

## Note operative
- DNS: narratour-review.com → zona su HOSTINGER
        narra-tours.com     → zona su CLOUDFLARE
- Segreti in /root/argo/.env (mai committato)

## Attriti
- **Due sessioni Claude Code parallele scrivono sullo stesso STATO.md**
  (10/9/2026, cantieri Panoptes-Mappa e Designer) — rischio di
  sovrascrittura reciproca: nessun lock, nessuna convenzione di sezione
  riservata per cantiere, solo append manuale in coda al file. Evitato oggi
  solo perché una delle due sessioni ha guardato `git status`/`git diff`
  prima di un `git add`, notato le modifiche dell'altra ed escluse dal
  proprio commit invece di sovrascriverle. Non è un meccanismo, è stata
  attenzione — la prossima volta potrebbe non esserci.

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

## Sessione 9/9/2026 — Cantiere Panoptes-Mappa, passo 1

**DEROGA regola del cantiere unico (9/9/2026, decisione di Leonardo):** cantiere Panoptes-Mappa aperto in parallelo a Regista Sonora v10. Motivo: macchine e repo separati (VPS vs PC Windows), zero interferenza, lavoro nei tempi morti d'ascolto del Regista. Prevista dal PIANO_OPERATIVO §1 ("se ne servono due in parallelo, si fa — annotandolo").

Prodotta la prima bozza `knowledge/mappa_sistema.yaml`, generata dal codice (sola lettura, nessun file di codice/config toccato). Cinque schede pipeline, non quattro come nominate all'apertura del cantiere — il codice mostra confini diversi, tre decisioni prese con Leonardo durante il piano:

- **`risposte_email`** unifica "lettura email IMAP" e "risposte email": nel codice è un'unica catena (`leggi_email → notifica_risposta → _valuta_e_rispondi → invia_risposta`), non due pipeline.
- **`manutenzione_sistema`** (nuova, non nominata): self-healing job + controlli periodici (15 min) + digest serale (22:00) — ha trigger ed effetti propri (alert Telegram, chiusura autonoma scadenze), non solo infrastruttura silenziosa.
- **`lead_gen_host`** (nuova, non nominata): cantiere lead-gen già chiuso operativamente, incluso su richiesta esplicita perché è codice reale e attivo nel repo, anche se ad attivazione manuale (script, non job/eventi).

`DA_VERIFICARE`/SOSPESO per scheda: `poster_host` 0, `risposte_email` 0, `dm_instagram_facebook` 1 (dedup_key su `triggered_at` grezzo, già noto), `manutenzione_sistema` 1 (l'inclusione stessa come scheda a sé, non componente condiviso — segnalata come nota, non bloccante), `lead_gen_host` 2 (pipeline manuale non a eventi; soglie di business non riverificate in questa sessione, fuori scope). Otto componenti in `condivisi` (`valuta_e_rispondi`, `invia_risposta`, `classificatore`, `drafter`, `approvazione_telegram`, `mailer`, `telegram_notifica`, `alert_una_volta`), tutti verificati con la regola del due via cross-import. `db_connect` escluso da `condivisi` per scelta (infrastruttura DB generica, non componente di dominio). `fuori_repo`: `regista_sonora`, `monta_audio`, `export_leadgen_windows` (Windows, `scheda: da_dichiarare`).

Campo `contratti` lasciato vuoto in ogni scheda come da istruzione — proposte riportate solo in chat, da confermare con Leonardo.

## Sessione 9/9/2026 — Cantiere Panoptes-Mappa, passo 2

Corretta `knowledge/mappa_sistema.yaml` (v2) sui punti indicati dal prompt del
passo 2 e riempito il campo `contratti` (18 contratti totali: 4 poster_host,
4 risposte_email, 4 dm_instagram_facebook, 4 manutenzione_sistema, 3
lead_gen_host, 3 su condivisi). Solo la mappa e questo file toccati, nessun
codice/config, nessun push.

**Contratti con `garantito_da: nessuno` (il risultato più importante di
questo passo — sono la lista dei test del prossimo cantiere):**
- **RE02** — "un bounce definitivo entra in soppressioni prima di
  qualunque altro invio a quell'indirizzo". La scrittura in soppressioni
  al bounce c'è (`worker/loop.py:392-398`), ma **nessun punto del codice
  legge `soppressioni` prima di inviare** una risposta automatica
  (`invia_risposta`) o un poster. La tabella oggi è scritta e mai
  consultata per bloccare un invio — solo letta in sola lettura dal
  digest e dall'export lead-gen. Se un indirizzo bounced/disiscritto
  scrivesse di nuovo, potrebbe ricevere una nuova bozza approvata e
  spedita senza che nulla se ne accorga. Divergenza più seria trovata in
  questo passo — riportata anche in DECISIONI APERTE sopra, backlog del
  cantiere email.
- **DM02** — "lo stesso DM non riceve mai due risposte". Confermato il
  sospetto già in mappa dal passo 1: `dedup_key = ghl-dm:{contact_id}:
  {triggered_at}` dedupe solo repliche esatte dello stesso webhook. Un DM
  reale rinviato da GHL con un `triggered_at` diverso genera un nuovo
  `event_id` e ripete l'intera catena (classificazione, bozza,
  approvazione, invio) da capo.

**Contratti con `garantito_da: eval`** (corretto dopo revisione di
Leonardo: non sono `nessuno`, sono proprietà di un output LLM che nessuna
guardia deterministica può verificare — appartengono a una suite di
valutazione con output atteso, non ai test di contratto):
- **CD01/CD02** (drafter) — "risponde solo con fatti in conoscenza.md" e
  "tono lei singolare": istruzioni nel system prompt
  (`brain/drafter.py:9-31`). Aggiunta una legenda dei valori ammessi per
  `garantito_da` in cima al file (`legenda_garantito_da`): codice
  `file:riga` · `test:<path>` · topologia (come MS04) · `eval` ·
  `nessuno`.

**Proposte del punto C che il codice non conferma come scritte (non
propriamente "smentite", ma l'assunzione implicita che ci si aspetterebbe
è falsa)**: le due sopra (RE02, DM02) sono gli unici casi — tutte le altre
10 proposte del punto C sono risultate vere e hanno un `garantito_da`
concreto in codice (vedi mappa).

**A1 — scritture non dichiarate, trovate rileggendo ogni scheda:**
oltre alle tre segnalate nel prompt (poster_host, dm_instagram_facebook,
risposte_email mancavano `events` in `scrive`), rileggendo scrittura per
scrittura sono emerse altre correzioni non richieste esplicitamente ma
reali:
- `dm_instagram_facebook` scriveva anche in `soppressioni` e `contacts`
  (via `_valuta_e_rispondi` condiviso, ramo soppressione) — mancavano
  entrambe.
- `risposte_email` e `dm_instagram_facebook` **leggevano** anche
  `approvals` e `messages` dentro `invia_risposta` (condiviso) — mancavano
  in `tabelle.legge`, non solo in `scrive`.
- `manutenzione_sistema` legge anche `alert_inviati` (digest_serale conta
  le caselle IMAP irraggiungibili da lì) — mancava in `legge`.
- `lead_gen_host` scriveva anche in `events` (risolvi.py, evento
  `prospect.places`) e leggeva `identities` (risolvi.py,
  `contatti_matchati`) — mancavano entrambe.
- `connectors/normalizza.py` e `connectors/fetch.py`: l'evidenza del
  passo 1 dichiarava già che restano nel campo `codice` di
  `lead_gen_host`, ma i due file non c'erano davvero nell'elenco —
  aggiunti.
- `connectors/llm.py` è importato direttamente sia da `brain/classifier.py`
  sia da `brain/drafter.py`: era nel `codice` solo di `classificatore`,
  aggiunto anche a `drafter` (con le stesse env, `ANTHROPIC_API_KEY` e
  `LLM_TETTO_GIORNALIERO`).

**A3 — caselle IMAP: 6 configurate, non una discrepanza.** `grep -o
'^MAILBOX_[0-9]*_USER' .env` trova **6** caselle (`MAILBOX_1`…`MAILBOX_6`):
sono le 4 attive più le 2 in warmup. Le altre 2 di cui parlava Leonardo il
9/9/2026 non sono ancora in `.env` — previsto passaggio a 8 quando
entreranno in warmup. Corretto in mappa (era segnato erroneamente come
DA_VERIFICARE in una prima stesura di questo passo).
Nota aggiuntiva emersa leggendo `connectors/imap_reader.py`: il filtro
warmup (`WARMUP_TAG` + pattern strutturale sull'oggetto) lavora sul
**contenuto** del messaggio, non sull'identità della casella — il codice
non sa quali `MAILBOX_N` sono "in warmup" nel senso operativo di Leonardo,
legge tutte le caselle configurate allo stesso modo.

**A6 — worker: una sola replica.** `docker-compose.yml` non dichiara
`deploy`/repliche per il servizio `worker` (default Compose: un solo
container). Confermata l'assunzione di `recover_orphaned_jobs`
(`worker/loop.py:1616-1625`): oggi è corretta, ma non è imposta dal
codice — solo dalla topologia del compose (contratto MS04, `garantito_da`
= il compose stesso, non una guardia applicativa).

**Altre correzioni di formato (A2/A5/B1):**
- `lead_gen_host.stato` → `concluso_roma` con nota (A4).
- `export_leadgen_windows` rimosso da `fuori_repo` (A5) — non
  corrispondeva a niente di reale.
- `env` riportate a regola unica: solo le env lette dal codice proprio
  della scheda; quelle dei condivisi (mailer, telegram_notifica,
  approvazione_telegram, classificatore, drafter, invia_risposta) stanno
  sulle rispettive schede condivise; `PG_PASSWORD` spostata in una nuova
  sezione `infrastruttura:` in fondo al file. Scoperta non ovvia:
  `REPLY_SMTP_USER` è letto direttamente dentro `invia_risposta`
  (condiviso, `worker/loop.py:1317`), non dentro `risposte_email` —
  spostato di conseguenza.
- `codice` di `worker/loop.py` portato a range di riga precisi per ogni
  scheda/condiviso, invece di descrizioni testuali.

**DA_VERIFICARE rimasti** (oltre al numero caselle IMAP sopra):
- soglie di business di `lead_gen_host` (punteggio export, blocklist
  placeholder) non riverificate riga per riga oltre a LG01-LG03.
- se/quando riaprire la replica di `lead_gen_host` su un'altra città resta
  fuori scope di questo passo (decisione operativa, non tecnica).

## Sessione 10/9/2026 — Cantiere Panoptes-Mappa, passo 4

Costruiti `scripts/panoptes/verifica_mappa.py` e `scripts/panoptes/impatti.py`
(più `scripts/panoptes/_mappa_lib.py`, funzioni pure condivise, e
`tests/test_panoptes_lib.py`, stile CASI). Zero LLM, zero dipendenze nuove
(PyYAML 6.0.1 già presente). Nessun file esistente toccato oltre a questo,
nessun push.

**`verifica_mappa.py`** — ricalcola dal codice i campi generabili di ogni
scheda (`tabelle.legge/scrive` via grep di INSERT/UPDATE/DELETE/SELECT sui
file/range dichiarati in `codice`, `env` via grep di `os.environ`/`os.getenv`,
`codice` via esistenza file + range dentro la lunghezza reale) e segnala le
divergenze in entrambe le direzioni (dichiarato-non-trovato = mappa vecchia;
trovato-non-dichiarato = mappa mente per omissione). Lancio:
```
python3 scripts/panoptes/verifica_mappa.py            # tutta la mappa
python3 scripts/panoptes/verifica_mappa.py --solo NOME # una sola scheda o condiviso
```
Exit 0 nessuna divergenza, 1 almeno una divergenza reale (gli "indecidibile"
non contano), 2 errore dello script (mappa non parsabile/mancante).

**`impatti.py`** — dato un file/riga, un componente condiviso, una tabella o
il `git diff` corrente, dice quali pipeline dipendono e quali contratti sono
in gioco, evidenziando quando le righe toccate cadono dentro il `garantito_da`
di un contratto ("← la modifica tocca la guardia stessa"). Lancio:
```
python3 scripts/panoptes/impatti.py --file worker/loop.py:1230
python3 scripts/panoptes/impatti.py --file worker/loop.py       # intero file
python3 scripts/panoptes/impatti.py --componente NOME
python3 scripts/panoptes/impatti.py --tabella NOME
python3 scripts/panoptes/impatti.py --diff [--esci-1-se-trasversale]
```
Exit 0 sempre (è informativo), salvo: 2 se `--componente`/`--tabella` non
esiste o `--file` punta a un path inesistente sul filesystem (vocabolario
chiuso, quasi certo refuso — deviazione dal contratto "exit 0 sempre" del
prompt originale, confermata con Leonardo); 1 con
`--esci-1-se-trasversale` se il risultato tocca più di una pipeline. Un
`--file` su un path esistente ma non mappato da nessuna scheda resta exit 0
con un messaggio esplicito ("la mappa non lo copre, non che sia innocuo") —
è il segnale che la mappa va estesa, non un "nessun impatto".

**Collaudo eseguito** (i cinque comandi + prova dell'esca, tutti verificati
leggendo il codice sorgente citato, non dati per buoni):
- `verifica_mappa.py` **non** esce pulito sulla mappa attuale: 6 divergenze
  reali trovate, riportate sotto invece che corrette qui (non era nello
  scope di questo passo, è il prossimo lavoro sulla mappa).
- `impatti.py --componente approvazione_telegram` → tocca `risposte_email` e
  `dm_instagram_facebook` (2 pipeline), come atteso.
- `impatti.py --tabella approvals` → tocca `risposte_email`,
  `dm_instagram_facebook`, `manutenzione_sistema` (3 schede), come atteso.
- `impatti.py --file worker/loop.py:1230` → dentro il `garantito_da` di RE01
  (e di DM04, stessa guardia), segnalato esplicitamente. DM01 correttamente
  escluso (il suo `garantito_da` 1234-1259 non fa overlap con la riga 1230).
- `impatti.py --file media/poster.py` → tocca **solo** `poster_host`, nessun
  altro. Granularità confermata.
- **Prova dell'esca**: rimossa a mano `messages` da `poster_host.tabelle.scrive`
  → `verifica_mappa.py --solo poster_host` fallisce con exit 1, nomina
  `messages` e `worker/loop.py:186`. Ripristinata (diff confrontato byte per
  byte con l'originale) → torna a exit 0.

**Le 6 divergenze reali trovate sulla mappa attuale** (non toccate in questo
passo — sono il prossimo lavoro, non un difetto dello script):
- `risposte_email` e `dm_instagram_facebook` scrivono `alert_inviati` (via
  `alert_una_volta`, condiviso, `worker/loop.py:755`) ma non lo dichiarano in
  `tabelle.scrive` — mancava anche a loro, come già successo per
  `manutenzione_sistema` prima del passo 2.
- `manutenzione_sistema.codice` dichiara `worker/loop.py:1554-1648`, ma il
  file ha 1647 righe — range fuori di uno.
- `approvazione_telegram.codice` (condiviso) dichiara
  `connectors/telegram.py:35-155`, ma il file ha 154 righe — stesso tipo di
  errore.
- `lead_gen_host.tabelle.legge` dichiara `events` e `soppressioni`, ma il
  grep non li trova: le uniche letture di quelle due tabelle passano da
  query costruite in una variabile (`query = "..."; cur.execute(query)`,
  in `scripts/export_prospect.py:92` ed `export_instantly.py:118`), che lo
  script segnala esplicitamente come `indecidibile` invece di ignorarle in
  silenzio — la dichiarazione della mappa resta comunque presumibilmente
  corretta, solo non confermabile da questo grep.

**Correzioni applicate subito dopo (stesso giorno, su richiesta di
Leonardo)** — le prime tre divergenze sopra erano errori veri della mappa,
non della verifica, e sono state corrette:
- `alert_inviati` aggiunta a `tabelle.scrive` di `risposte_email` e
  `dm_instagram_facebook`, con evidenza che cita il passaggio via
  `alert_una_volta` (`worker/loop.py:749-764`).
- `manutenzione_sistema.codice`: `worker/loop.py:1554-1648` → `1554-1647`
  (il file ne ha 1647). `approvazione_telegram.codice`:
  `connectors/telegram.py:35-155` → `35-154` (il file ne ha 154).
- La quarta (events/soppressioni di `lead_gen_host`) **non** era un errore
  della mappa — verificata a mano al passo 2, è il grep che non arriva.
  Introdotto un nuovo campo opzionale nella mappa, `verifica.indecidibile`
  su una scheda, per dichiararlo esplicitamente invece di lasciarlo come
  falso allarme perenne:
  ```
  verifica:
    indecidibile:
      - campo: tabelle.legge      # o tabelle.scrive, o env
        valore: events
        motivo: >
          spiegazione libera del perché il grep non può confermarlo,
          e perché si sa comunque che è vero
  ```
  `verifica_mappa.py` lo consulta prima di segnalare un "dichiarato ma non
  trovato": se il valore è coperto da un'eccezione dichiarata, non conta
  come divergenza ma resta visibile in output con l'etichetta
  `[indecidibile atteso, dichiarato]` e il motivo per intero — non sparisce
  mai in silenzio, per lo stesso principio degli `indecidibile` trovati dal
  grep. Si applica **solo** alla direzione "dichiarato ma non trovato": la
  direzione opposta ("trovato ma non dichiarato", quella che la prova
  dell'esca collauda) non guarda affatto questo campo, quindi non può
  essere usato per nascondere un problema nuovo — solo per confermare una
  lettura già verificata a mano.
  Rilancio dopo le correzioni: `verifica_mappa.py` esce **0**, con 2
  indecidibili (le query in variabile di `export_prospect.py`/
  `export_instantly.py`, invariati) e 2 indecidibili attesi/dichiarati
  (`events`/`soppressioni` di `lead_gen_host`, ora coperti dal nuovo campo).
  Prova dell'esca ripetuta con lo stesso meccanismo attivo: rimossa di nuovo
  `messages` da `poster_host.tabelle.scrive` → fallisce ancora con exit 1,
  nomina `messages` e `worker/loop.py:186` — il nuovo campo non ha
  disattivato la verifica, perché copre solo l'altra direzione. Ripristinata
  → torna a 0.

**Limiti incontrati, riportati per intero come richiesto — dicono quanto
fidarsi della verifica automatica:**
- **Query costruita in una variabile, non nel corpo di `.execute(...)`**: lo
  stile prevalente del repo (`worker/loop.py`, `backend/main.py`) scrive il
  testo SQL direttamente dentro `cur.execute("...")`; alcuni script di
  `lead_gen_host` (`export_prospect.py`, `export_instantly.py`) costruiscono
  la query in una variabile con `query = "..."` / `query += "..."` su più
  righe e poi chiamano `cur.execute(query)`. Il grep non insegue variabili:
  quando il primo argomento di `.execute(...)` è un identificatore nudo
  senza virgolette, lo script lo segnala come `indecidibile` (mai come
  "non trovato" silenzioso) invece di provare a ricostruire la query
  risalendo alle assegnazioni precedenti — sarebbe più completo ma fragile
  (riassegnazioni condizionali, variabili riusate). Falso positivo
  accettato: un `indecidibile` in più da leggere a mano.
- **`SELECT` senza `FROM`** (es. `SELECT setseed(%s)`, usato per rendere
  deterministico un campionamento casuale in `estrai_email.py`/
  `estrai_social.py`): non è indecidibile, è semplicemente una query senza
  tabella — lo script lo riconosce e lo ignora silenziosamente invece di
  segnalarlo come incertezza (sarebbe stato rumore puro).
- **Env dichiarata come pattern** (`MAILBOX_{n}_USER/PASS` in
  `risposte_email`, l'unico caso nella mappa): non è un nome pulito
  confrontabile per uguaglianza. Lo script riconosce la sintassi `{n}` e
  verifica solo che esista almeno una variabile trovata col prefisso
  dichiarato (`MAILBOX_` seguito da una cifra), senza pretendere di
  ricostruire i suffissi esatti (`_USER`/`_PASS`) dal testo libero — un
  refuso nel prefisso stesso non verrebbe preso.
- **Env "indiretta"**: una funzione wrapper che legge env per conto di
  un'altra (es. `password_per()` in `imap_reader.py`, che richiama
  `_mailboxes()` senza leggere env essa stessa) è vista correttamente SOLO
  perché l'intero file è dichiarato senza range in `codice` — se un domani
  un helper così vivesse in un file diverso da quello dichiarato, il grep
  non lo troverebbe. Nessun caso reale oggi, limite strutturale dello
  strumento (guarda solo i file dichiarati, non segue le chiamate).
- **Annidamento parziale env pipeline/condiviso**: vedi nota in DECISIONI
  APERTE sopra (`alert_una_volta` dentro `manutenzione_sistema`).
- **`garantito_da` con più range sullo stesso file** (solo PH04 nella mappa
  attuale, forma `file.py:186-193,246-253,294-301`): gestito esplicitamente,
  altrimenti un `finditer` naive perde tutti i range dopo il primo — un vero
  falso negativo, non solo un'imprecisione estetica.
- **`impatti.py` su una query a file intero** (bare, senza riga) tratta
  l'intero file come range effettivo per il filtro overlap dei contratti:
  un contratto il cui `garantito_da` cita una riga qualunque di quel file
  compare come "in gioco", anche se la modifica reale toccherà solo una
  parte del file. Falso positivo voluto (coerente con "meglio segnalare di
  troppo"), non un bug.

**Chiusura: non ancora (10/9/2026).** Il cantiere Panoptes-Mappa non è
chiuso, ma non per lavoro tecnico residuo: la formalizzazione del test di
accettazione è soddisfatta (vedi sotto, esito "pieno", commit `53b53a4`) e
non è più tra le cose mancanti. Resta solo la settimana di uso reale
(verificare che `impatti.py`/`verifica_mappa.py` vengano davvero consultati
prima di una modifica, non solo che esistano) — **chiusura prevista
17/9/2026, salvo incoerenze emerse dall'uso**.

Un primo test è stato eseguito il 10/9/2026 con esito positivo, ma non in
condizioni di sessione indipendente: alla domanda naturale "cosa rischio se
modifico il gate di approvazione Telegram?", posta nella STESSA sessione di
lavoro in cui gli script erano appena stati costruiti (non una sessione
fresca, senza contesto pregresso sul cantiere), la risposta è arrivata
lanciando spontaneamente `impatti.py --componente approvazione_telegram`
(nessuna istruzione esplicita a usare lo strumento), individuando la
trasversalità su due pipeline (`risposte_email`, `dm_instagram_facebook`) e
la fragilità della catena RE01/DM04 → `approvazione_telegram` (vedi nota
aggiunta a `garantito_da` di RE01/DM04 in `mappa_sistema.yaml`, 10/9/2026).
Segnale positivo ma parziale: dimostra che lo strumento produce
l'informazione giusta quando qualcuno lo usa, non che una sessione/operatore
senza il contesto appena caldo lo scopra e lo usi da solo.

Quel secondo test è stato fatto lo stesso giorno (10/9/2026), in una
sessione indipendente: nessun contesto pregresso sul cantiere Panoptes,
aperta da zero sulla stessa domanda ("cosa rischio se modifico il gate di
approvazione Telegram?"). La sessione ha letto `mappa_sistema.yaml` di sua
iniziativa — contratti RE01/DM04, la nota sulla catena a due anelli, la
scheda `approvazione_telegram` con `usato_da`, `evidenza` ed `env` — e ha
costruito la risposta sui contratti dichiarati (trasversalità sulle due
pipeline, fragilità della catena di fiducia, confine di autenticazione del
webhook), non su una lettura ad-hoc del codice scollegata dalla mappa.
Esito positivo. **Esito complessivo del test di accettazione: pieno**, non
più parziale — copre sia "lo strumento produce l'informazione giusta" sia
"una sessione senza contesto pregresso la scopre e la usa da sola".

**Deroga alla regola del cantiere unico (10/9/2026, decisione di
Leonardo):** Panoptes-Mappa è bloccato solo dal calendario (l'attesa della
settimana di uso reale sopra), non da lavoro tecnico residuo — condizione
prevista dal PIANO_OPERATIVO §1 per i cantieri bloccati da attese. Il
prossimo cantiere, **Argo — la voce**, si apre in parallelo.

**Documento di cantiere:** vive su un'altra macchina, non in questo repo
(coerente con la DEROGA del 9/9/2026 su Regista Sonora — macchine e repo
separati). Non cercato in questo repo; la sua chiusura formale resta a
carico di Leonardo.

## Sessione 2026-09-10 — Cantiere Designer, passo 2 Fase B

Bonifica dei blocchi salvati di `yourservice-it` (mai la pagina live — solo
i file in `pagine/yourservice-it/`, incolla in GHL su pagina di prova resta
di Leonardo, Fase C). Testo di fedeltà N.1 confermato prima di intervenire:
ricomposizione locale degli 8 blocchi (`pagine/yourservice-it/_ricomposizione/`,
script `costruisci.py`) via `pavimento.mjs`, riproduce h1:2, crash React
(`useTweaks is not defined`), 404-equivalente su `tweaks-panel.jsx` — commit
`1c387f0`.

**Fatto:**
- **Sistema React morto rimosso** da `blocco_body_mobile_per_host.html`: 3
  script CDN (react/react-dom/babel da unpkg.com), i contenitori
  `#hero-root`/`#tweaks-root`, l'intero blocco `<script type="text/babel">`
  con le 9 varianti mai visibili e i marcatori EDITMODE, più la regola CSS
  `#hero-root{...}` rimasta orfana. Verificato: errore pagina
  `useTweaks is not defined` sparito, risorsa `tweaks-panel.jsx` non più
  richiesta. Peso locale sceso da 6383 KB/287 richieste a 5483 KB/270
  richieste (misura solo indicativa, non è l'intera pagina — verifica vera
  su `/preview/` in Fase C, per regola di modalità).
- **Contrasto footer corretto**: alpha 0,25→0,5 (`.nt-footer-copy`,
  `.nt-footer-legal a`), 0,42→0,5 (`.nt-footer-tagline`), 0,35→0,5
  (`.nt-footer-col-title`, trovata dal pavimento durante la verifica, non
  nella ricognizione iniziale) — tutte sullo stesso colore dichiarato, solo
  più opache. Verificato con axe: zero violazioni residue sul footer.

**H1 doppio — risolto correggendo lo strumento, non la pagina (decisione di
Leonardo).** Il `display:none` reciproco a 861px (applicato, verificato
senza finestra morta 820-900px) lasciava comunque "h1: 2" nel pavimento:
`pavimento.mjs` contava i nodi grezzi del DOM, non l'albero di
accessibilità. Due h1 nel sorgente sono HTML5 valido finché uno solo è
esposto — un microscript per rimuoverlo dal DOM sarebbe stato più fragile
(GHL lazy-load i custom code, flash quasi garantito) per un problema che
non esiste lato accessibilità/SEO. Corretto `pavimento.mjs`: ora conta gli
h1 esposti (non dietro `display:none`/`visibility:hidden`/`[hidden]`/
`aria-hidden`), il conteggio grezzo resta come nota informativa. Rimisurato
dopo la correzione: **1 h1 esposto** su `yourservice-it` bonificato —
chiuso. Dettagli in `modalita/narratours.md` §9; nota che la baseline del
passo 1 ("h1: 2" su tutte e 6 le pagine) fu misurata col criterio vecchio,
da rileggere con questa nota se si riconfronta.

**Duplicazione desktop/mobile del markup — debito unico, non risolto qui.**
Causa comune a tre sintomi: markup desktop/mobile duplicato, mai rimosso
dal DOM (solo nascosto per viewport). H1 doppio (sopra, chiuso lato
criterio, non lato struttura); **6 iframe Vimeo su 3 video distinti**
duplicati desktop+mobile (non 7 come nell'orientamento del cantiere); **2
iframe form GHL con lo stesso id** (`inline-bfJq2874KQlSBFYmxq87`)
duplicati tra `blocco_03.html` e `blocco_body_mobile_per_host.html` — non
isolato con certezza come causa di un errore console specifico (rumore
Cloudflare Turnstile nell'ambiente di test, vedi sotto). Rimedio comune:
unificare in un markup responsive unico — candidato principale del
prossimo intervento, non di questa Fase B. Dettagli in
`modalita/narratours.md` §8.

**Oro come testo su sfondo chiaro — fuori perimetro, debito di brand.**
`#c49a3c` su crema/bianco è 2,48–2,61:1 (WCAG richiede 4,5, o 3 per testo
grande — non lo raggiunge nemmeno quello). Colore di brand usato su tutto
il sito: non corretto solo su questa pagina per non creare incoerenza tra
pagine. Tre opzioni con rapporti calcolati in `modalita/narratours.md` §8,
nessuna scelta.

**Trovato, non nel perimetro di questa bonifica:**
- CSS orfano preesistente e indipendente dal sistema React
  (`.hero`/`.hero-card`/`.hero-logo`/`.hero-badge`/`.hero-cards`/
  `.calc-note` in `blocco_body_mobile_per_host.html`, nessun markup
  corrispondente) — candidato per un prossimo micro-intervento, basso
  rischio.
- **(risolto 10/9/2026)** Livello titoli saltato (h2→h4 in due punti,
  `.risk-card`/`.guest-item`): tag corretti in h3, stile spostato su classe
  dedicata (`.risk-card-title`/`.guest-item-title`) invece che sul
  selettore di tag — zero cambiamenti visivi, verificato con
  `getComputedStyle` (stesso bounding box in pixel prima/dopo). Pavimento
  titoli: FAIL → PASS.

**Limite di piattaforma scoperto (documentato in `modalita/narratours.md`
§8):** in questo ambiente di sviluppo (non il VPS di produzione), il widget
GTranslate e/o il form GHL innescano una sfida Cloudflare Turnstile che
blocca indefinitamente l'evento `load` di Playwright — confermato sia sulla
pagina live sia sulla ricomposizione locale. `blocco_gtranslate.html`
escluso dalla ricomposizione per completare i test (la sua posizione nel
builder era comunque già "DA CONFERMARE"). Se ricapita dal VPS reale, non
sospettare i blocchi prima di aver controllato lo stesso meccanismo.
Genera anche rumore run-to-run su richieste/errori console: il peso in KB
resta il numero stabile per confrontare stati diversi (§10 di
`modalita/narratours.md`).

**Footer/Header confermati globali — fix nel repo, non incollato in Fase
C (10/9/2026).** Verificato su richiesta di Leonardo prima della consegna:
sono Header/Footer Tracking, condivisi a livello sito (commento nei file +
`document.title` identico su tutte e 6 le pagine in baseline). Il fix di
contrasto footer resta committato ma esce dalle istruzioni d'incolla —
tocca tutte le pagine live insieme. **Rischio segnalato, non risolto**: la
regola di modalità per il `noindex` della pagina di prova assumeva
l'Header Tracking come "per pagina" — se è davvero condiviso, quella regola
deindicizzerebbe l'intero sito. Marcato `[CONTRADDETTO]`, da verificare
prima di creare la pagina di prova.

File toccati (oltre a quelli già elencati sopra): correzione ai 5 salti di
titolo in `blocco_body_mobile_per_host.html`;
`modalita/narratours.md` (§8 estesa, §10 nuova su divergenza locale/live,
nuova regola 6 locale/globale). Commit locali (`93eb9ec`, `aef5500`,
`718a9a3`, `10ea317`), niente push. Questa sezione di STATO.md è scritta ma
**non committata**: il file aveva già modifiche non committate del
cantiere Panoptes-Mappa (`git status` a inizio sessione) che non andavano
mescolate nel commit Designer — segnalato a Leonardo, resta nel working
tree.

## Sessione 2026-09-10/11 — Cantiere Designer, passo 2 Fase C (parziale, FERMATA)

Test di fedeltà N.2 sull'anteprima GHL. Leonardo ha duplicato `yourservice-it`
in una pagina di prova su GHL e incollato i 3 blocchi bonificati
(`blocco_01`, `blocco_hero_mobile_v3`, `blocco_body_mobile_per_host`).
Header/footer/tracking sono i globali del sito, non toccati. Pagina salvata,
mai pubblicata. URL:
`https://sites.leadconnectorhq.com/preview/73YTL2ucKSWVe4jGSuRC`.

**Regola noindex annullata e sostituita** — vedi bullet sopra e
`modalita/narratours.md` §2 regola 4.

**1. Verifica incolla — OK.** Assenti sull'anteprima: script CDN
React/ReactDOM/Babel (0 richieste `unpkg.com`), richiesta `tweaks-panel.jsx`
(0), crash `useTweaks` (0 in console/pageerror), `#hero-root`/`#tweaks-root`
(assenti dal DOM). L'incolla è andato a buon fine.

**2. Peso — PASS su entrambe le varianti, sotto la baseline.**
| Variante | KB totali | Richieste | KB immagini | Primo render |
|---|---:|---:|---:|---:|
| `?notrack=true` | 5913 | 328 | 731 | 1980 ms |
| senza `notrack` | 5836 | 323 | 730 | 1264 ms |

Baseline live `yourservice-it` (misurata 09/09/2026, prima della bonifica):
**6053 KB**. Differenza tra le due varianti (77 KB, 5 richieste) piccola,
compatibile con il rumore run-to-run di Cloudflare Turnstile già
documentato (`modalita/narratours.md` §10), non un effetto sistematico di
soppressione tracking da parte di `notrack=true`. **Variante usata per il
confronto omogeneo con la baseline: senza `notrack`** (la baseline live non
ha soppressioni). **5836 KB contro 6053 KB — la bonifica pesa 217 KB in
meno (-3,6%)**, pagina intera contro pagina intera.

**3. Test anti-finestra-morta esteso all'anteprima reale — FALLITO.**
Finestra morta **768-860px inclusi** (9 larghezze testate:
820/840/855/859/860/861/865/880/900 — le prime 5 sono morte, le ultime 4
OK). Vedi bullet RISCHIO sopra per l'analisi della causa. Screenshot di
verifica in `.claude/skills/designer/output/finestra-morta_*.png`
(gitignored): 767px mostra l'hero mobile, 768px salta all'header→seconda
sezione senza hero, 861px mostra l'hero desktop.

**FERMATA qui, come da istruzione**: non eseguiti il test di fedeltà N.2
completo (locale vs anteprima) né la chiusura dei `[DA VERIFICARE]` residui
— quelli restano aperti fino alla decisione di Leonardo sulla soglia
768/861.

**Script ad-hoc aggiunti** (stesso pattern di `test_anti_finestra_morta.mjs`
di Fase B, non tool permanenti della skill) in
`pagine/yourservice-it/_ricomposizione/`: `test_anti_finestra_morta_preview.mjs`
(stesso test ma contro l'URL `/preview/` invece del file locale),
`verifica_incolla_preview.mjs` (verifica assenza residui React),
`screenshot_finestra_morta.mjs` (cattura le larghezze di confine). Nota
tecnica: questi script (come quello di Fase B) non risolvono `playwright`
se eseguiti dalla loro cartella — vanno lanciati con `node_modules` di
`.claude/skills/designer` raggiungibile (es. copiati lì per l'esecuzione,
poi il sorgente canonico resta nel repo). Non è un problema introdotto qui,
preesisteva nel copione di Fase B.

File toccati: `modalita/narratours.md` (§2 regola 4 riscritta,
`[CONTRADDETTO]` rimosso), questa sezione di STATO.md, i 3 script ad-hoc
sopra. Nessuna modifica al sito live, nessun push.

## Sessione 2026-09-11 — Cantiere Designer, Fase C, misura sulla LIVE intatta (nessuna implementazione)

Su richiesta di Leonardo, prima di scegliere la soglia per il fix h1: misura
sulla pagina live originale `https://narra-tours.com/yourservice-it` (mai
toccata dal cantiere), a 375/767/768/800/830/860/861/900/1024px.

**Risultato: sulla live NON esiste alcuna finestra morta.** A ogni
larghezza testata risulta esposta esattamente 1 hero e 1 h1 (criterio
`pavimento.mjs`). GHL nasconde/mostra le colonne con tre classi di
piattaforma (CSS inline, non nei blocchi): `.desktop-only` sotto
`max-width:767px`, `.tablet-hide` sotto `min-width:768px e max-width:1024px`,
`.mobile-only` sotto `min-width:1024.02px` — confine reale **767/768px**.
Dettagli e valori in `modalita/narratours.md` §2 (nuova sezione "Breakpoint
reale di visibilità colonna").

**Causa della finestra morta 768-860 trovata sull'anteprima (sessione
precedente): è nostra, non preesistente.** Sulla live, GHL da solo mostra
già l'hero desktop pulito a partire da 768px (nessun collasso, nessuna
rottura — screenshot inviati a Leonardo). Il `display:none` reciproco
aggiunto in Fase B su `.nt-p1-hero` (soglia 861px, presa in prestito da
`blocco_01.html`, mai misurata sulla piattaforma) è ciò che sopprime
l'hero desktop tra 768 e 860 sull'anteprima bonificata — GHL da solo non
lo avrebbe mai nascosto lì.

**Raccomandazione (dati, non ancora implementata): IPOTESI 1 — il fix
Fase B era superfluo.** Rimuovere il `display:none` reciproco aggiunto in
Fase B da `blocco_01.html` e `blocco_hero_mobile_v3.html`, lasciare che
GHL gestisca la visibilità nativamente (come fa già sulla live). Elimina
la finestra morta, elimina una soglia indovinata, meno codice. Nessun bug
preesistente sulla live da registrare (verificato: nessuna finestra morta
768-860 sulla pagina intatta). Ipotesi 2 (allineare la soglia a 768) e
Ipotesi 3 (estendere l'hero mobile oltre il confine GHL) non valutate oltre:
l'Ipotesi 1 risolve il problema senza bisogno di codice aggiuntivo.
**Decisione e implementazione restano a Leonardo — nessuna modifica ai
blocchi fatta in questa sessione.**

File toccati: `modalita/narratours.md` (nuova sezione breakpoint reale +
regola "non prendere in prestito una soglia"), questa sezione di
`STATO.md`. Nessun commit, nessun push, nessuna modifica al sito live o
ai blocchi bonificati. Test anti-finestra-morta completo sull'anteprima
(tutte le larghezze, non solo 820-900) resta da fare dopo l'implementazione
della soluzione scelta.

## Sessione 2026-09-11 (continua) — Cantiere Designer, Fase C, via libera Ipotesi 1

Via libera di Leonardo su Ipotesi 1 (vedi sessione precedente). Eseguito:

**1. Rimozione fix Fase B.** Rimosso da `blocco_01.html` il blocco
`@media (max-width:860px) { .nt-p1-hero { display:none; } }` (con il suo
commento) e da `blocco_hero_mobile_v3.html` il blocco
`@media (min-width: 861px) { #ntHero { display: none; } }` (con il suo
commento). Verificato: `git diff 771185a -- pagine/yourservice-it/blocco_01.html
pagine/yourservice-it/blocco_hero_mobile_v3.html` è **vuoto** — i due file
sono tornati identici all'originale pre-bonifica su questo punto, nessuna
differenza residua.

**2. Test anti-finestra-morta locale ripetuto, con CSS di piattaforma
riprodotto.** Aggiunto `pagine/yourservice-it/_ricomposizione/css_piattaforma_ghl.html`
(le tre classi `.desktop-only`/`.tablet-hide`/`.mobile-only` misurate sulla
live, applicate direttamente a `.nt-p1-hero`/`#ntHero` — la ricomposizione
locale non ha la struttura a colonne di GHL, quindi le soglie sono
applicate ai selettori delle hero invece che a un wrapper inesistente in
locale). `costruisci.py` aggiornato per includerlo. `test_anti_finestra_morta.mjs`
aggiornato alle larghezze richieste (375/767/768/800/830/860/861/900/1024,
non più solo 820-900). Risultato: **PASS**, esattamente una hero a ogni
larghezza — stesso esito della live, il locale è ora rappresentativo.
`pavimento.mjs` sulla ricomposizione aggiornata: **h1 esposti: 1** (invariato
rispetto a prima della rimozione — confermato che il fix non serviva a
nulla anche col criterio nuovo).

**3. Baseline corretta.** Aggiunta nota in `baseline_narratours.md` accanto
alla tabella del pavimento (colonna H1): il "2" era un falso positivo del
criterio vecchio (nodi grezzi del DOM), non un bug delle pagine — su
`yourservice-it` col criterio nuovo (h1 esposti) risultava già 1 su tutte
le larghezze testate sulla live, prima di qualunque intervento. Le altre 5
pagine non sono state rimisurate: nota esplicita che il loro "2" resta da
verificare, non da assumere. Stessa correzione anche in
`modalita/narratours.md` §8 (vicino alla voce H1 doppio esistente).

**5. Lezione di metodo in modalità.** Aggiunta in `modalita/narratours.md`
§2, accanto alla lezione di piattaforma (breakpoint reale) già scritta
nella sessione precedente: prima di correggere un FAIL del pavimento,
verificare che il problema esista davvero sulla piattaforma di
destinazione — un criterio di misura sbagliato può inventare un problema,
e il fix di un problema inesistente ne crea uno vero. Regola operativa:
nessun fix responsive entra in un blocco senza che il comportamento della
piattaforma sia stato misurato prima (pagina live o anteprima, mai solo il
locale).

**4. Prossimo passo (non eseguito qui): Fase C dal punto 4.** In attesa
che Leonardo reincolli `blocco_01.html`/`blocco_hero_mobile_v3.html`
corretti sulla pagina di prova (salvata, non pubblicata) e dia il via
libera a ripetere pavimento + anti-finestra-morta sull'anteprima reale.
Poi test di fedeltà N.2 e chiusura dei `[DA VERIFICARE]` residui.

File toccati: `pagine/yourservice-it/blocco_01.html`,
`pagine/yourservice-it/blocco_hero_mobile_v3.html` (rimozione),
`pagine/yourservice-it/_ricomposizione/costruisci.py`,
`pagine/yourservice-it/_ricomposizione/css_piattaforma_ghl.html` (nuovo),
`pagine/yourservice-it/_ricomposizione/test_anti_finestra_morta.mjs`,
`pagine/yourservice-it/_ricomposizione/ricomposizione.html` (rigenerato),
`modalita/baseline_narratours.md`, `modalita/narratours.md`, questa
sezione di `STATO.md`. Commit locale a fine sessione, niente push, nessuna
modifica al sito live.

## Sessione 2026-09-10 — Cantiere Argo — la voce, fondamenta

Cantiere nuovo, aperto in parallelo a Panoptes-Mappa (deroga già annotata
sopra: Panoptes è bloccato solo dal calendario, non da lavoro tecnico
residuo). **Cos'è Argo — la voce** (dettaglio in `knowledge/argo/IDENTITY.md`):
l'unica entità con cui Leonardo parla. Non coordina il sistema (quello resta
Panoptes): capisce le intenzioni di Leonardo e le traduce in mandati verso
l'orchestratore, legge lo stato del sistema e ne riferisce una cosa alla
volta. Guardrail centrale: **Argo traduce, non origina** — ogni mandato deve
essere riconducibile a un messaggio esplicito di Leonardo.

Sessione di sole fondamenta: **zero LLM, zero bot, zero Telegram**, come da
istruzione. Fatto:
- Migrazione `db/migrations/006_osservazioni_mandati.sql`: tabelle
  `osservazioni` (append-only, scrive Panoptes, legge Argo; `stato`
  `nuova|riferita|archiviata`, unico campo che Argo cambia; `dedup_key`
  unica; indice su `stato`) e `mandati` (scrive Argo verso l'orchestratore;
  `origine_msg NOT NULL` è il guardrail "Argo traduce, non origina" reso
  vincolo di schema; indice parziale su `esito IS NULL` per i mandati
  ancora aperti, stesso pattern di `messages_thread_canale_direzione_uniq`).
  Applicata (`docker exec -i argo-db-1 psql -U argo -d argo < ...`) e
  verificata con `\d osservazioni`/`\d mandati`. `db/schema.sql` aggiornato
  in coda con le stesse due tabelle, come dopo ogni migrazione precedente.
- File di identità in `knowledge/argo/`: `SOUL.md`, `IDENTITY.md`,
  `USER.md` — contenuto fornito da Leonardo, creati testuali senza
  riscritture.
- `knowledge/mappa_sistema.yaml` (v2→v3): nuova sesta scheda pipeline
  `argo_voce` (stato `fondamenta`, `tabelle.legge/scrive` intenzionalmente
  vuote — nessun file `.py` le tocca ancora, `codice` elenca solo la
  migrazione e i tre file di identità) con due contratti: **AV01**
  ("nessun mandato senza `origine_msg`", garantito dal vincolo NOT NULL,
  `db/migrations/006_osservazioni_mandati.sql:18`) e **AV02** ("solo Argo
  aggiorna `osservazioni.stato`", `garantito_da: nessuno` — enunciato
  aspirazionale, stesso trattamento di RE02/DM02: lista dei test/eval del
  prossimo cantiere, non un difetto della mappa). `verifica_mappa.py`
  rilanciato sull'intera mappa: **exit 0**, 14 schede verificate, nessuna
  divergenza (solo i 2 indecidibili e i 2 indecidibili-attesi già noti di
  `lead_gen_host`).
- Revisione guardrail (subagent `guardrail-review`) sul diff: nessuna
  violazione bloccante (niente segreti, niente ORM/Alembic, niente bypass
  di `approvals`, AV01 verificato riga per riga contro il file reale). Un
  punto segnalato per il prossimo cantiere, riportato sotto in "Resta da
  fare": `mandati` non ha oggi alcun meccanismo di idempotenza (niente
  `dedup_key`, niente claim atomico) — non un problema ora (nessun writer
  esiste), ma da risolvere prima che Argo scriva mandati veri, altrimenti
  un retry/riavvio potrebbe duplicarli.

**DEROGA alle sei tabelle base dello schema (10/9/2026, motivata).** Lo
schema iniziale (`contacts, identities, events, messages, approvals, jobs`)
è cresciuto nel tempo (`alert_inviati`, `soppressioni`, colonne prospect) ma
sempre dentro la semantica già esistente di quelle tabelle. `osservazioni` e
`mandati` sono le prime due tabelle per un sottosistema diverso — Argo,
l'interlocutore — e non si adattano a quella semantica: `events` è per
eventi di dominio con `dedup_key` da trigger esterni (webhook, IMAP), non
per segnalazioni interne di Panoptes; `messages` traccia le conversazioni
con host/prospect, non la comunicazione tra sottosistemi interni. Due
tabelle nuove, motivate da un dominio nuovo, non un'astrazione prematura.

**DEROGA puntuale alla convenzione "niente CHECK" (10/9/2026, decisione di
Leonardo, motivata).** Nessuna tabella del repo usava finora un vincolo
`CHECK` (gli enum di stato — `approvals.stato`, `jobs.stato` — sono sempre
stati enforcement applicativo, mai a livello di schema). `osservazioni.stato`
e `mandati.tipo` sono la prima eccezione: due `CHECK` (`stato IN ('nuova',
'riferita','archiviata')`, `tipo IN ('consultazione','esecuzione')`).
Motivo: sono gli enum su cui poggia direttamente il guardrail "Argo traduce,
non origina" — un `tipo` fuori enum aprirebbe una terza categoria di mandato
mai prevista, senza che nulla lo impedisca a livello di schema (a differenza
degli altri enum del repo, che non reggono un guardrail di sicurezza ma solo
uno stato applicativo). Deroga puntuale, non una nuova convenzione generale:
resta da valutare caso per caso altrove.

**Resta da fare** (prossimo cantiere, fuori scope di questa sessione): bot
Telegram separato per Argo (il bot meccanico esistente non si tocca);
connettore LLM per capire i messaggi di Leonardo e tradurli in mandati;
implementazione dei tre modi (instrada/avvisa/orienta, dettaglio in
IDENTITY.md) che leggono `approvals`/`jobs`/`escalations`/`osservazioni`/
`STATO.md`/git; popolamento reale di `USER.md` con l'uso, col consenso di
Leonardo ad ogni voce (regola 1 del file stesso).
**Segnalato dalla revisione guardrail**: `mandati` non ha oggi nessun
meccanismo di idempotenza (`dedup_key` o claim atomico) — quando Argo
scriverà mandati veri da messaggi di Leonardo, un retry/riavvio potrebbe
scriverne due per lo stesso messaggio. Non un difetto della migrazione
(nessun writer esiste ancora, coerente con l'invariante "ogni handler deve
poter girare due volte senza danni" che oggi non si applica perché non c'è
alcun handler), ma va risolto prima di scrivere il codice che popola questa
tabella.

File toccati: `db/migrations/006_osservazioni_mandati.sql` (nuovo),
`db/schema.sql`, `knowledge/argo/{SOUL,IDENTITY,USER}.md` (nuovi),
`knowledge/mappa_sistema.yaml`, questa sezione di `STATO.md`. Nessun
commit, nessun push (lo fa Leonardo, istruzione esplicita).

## Sessione 2026-09-10/11 — Cantiere Argo — la voce, lettori di stato

Prosecuzione delle fondamenta (sopra): prima di un bot o un connettore LLM,
Argo deve poter leggere lo stato reale del sistema. Sessione di sola
lettura: zero LLM, zero Telegram, zero bot, nessuna scrittura su nessuna
tabella (nemmeno `osservazioni.stato`).

**Decisione con Leonardo — accesso al DB dell'harness.** Il container `db`
non espone la porta a host, quindi psycopg diretto da uno script lanciato
sull'host non arriva. Tre opzioni proposte; scelta: **da host, via `docker
exec argo-db-1 psql`** (stesso comando già in CLAUDE.md §Comandi). L'harness
gira interamente sull'host con un solo comando: `STATO.md` e git si leggono
nativamente dal repo, le query DB automatizzano lo stesso `docker exec` che
Leonardo già usa a mano, avvolte in `SELECT json_agg(t) FROM (<query>) t`
per un parsing robusto (JSON, non delimitatori fragili su testo libero).
Zero modifiche a Dockerfile/docker-compose.yml/.env, zero redeploy, zero
nuove dipendenze. **Deviazione dichiarata dalla convenzione "psycopg
diretto"**: `argo/stato.py` è un tool diagnostico lanciato a mano, non
codice di pipeline — non gira mai nel worker/API, non usa `PG_PASSWORD`
(l'exec nel container usa l'auth locale trust già in uso per `docker exec
-it argo-db-1 psql`).

**Fatto:**
- **`argo/stato.py`** (nuovo pacchetto): sei funzioni di sola lettura, ognuna
  ritorna `{"copertura": "completa"|"parziale"|"assente", "motivo": ..., ...}`
  — mai una copertura finta, come richiesto da `knowledge/argo/IDENTITY.md`
  ("Argo deve poter dire 'vedo le tabelle ma non lo stato di X'").
  1. `approvazioni_in_attesa()` — stessa query/JOIN di
     `_controllo_approvazioni_bloccate` (`worker/loop.py`). Copertura
     completa.
  2. `job_falliti()` — tre liste: falliti (aggregati per tipo+errore, non
     riga per riga — 111 righe `failed` reali nel DB oggi sarebbero rumore
     puro elencate una a una), fermi (`stato='running'`), in coda da troppo
     (`pending` con `run_after` più vecchio di 10 minuti, soglia dichiarata
     e arbitraria). Copertura parziale: `jobs` non ha `updated_at`/
     `started_at`, solo `created_at` — per i job `running` l'età mostrata è
     un'approssimazione (buona per i job perenni ricreati ad ogni giro,
     meno per un job con più tentativi).
  3. `escalation_aperte()` — `escalations` **non esiste** (né schema, né
     DB, né codice — confermato anche in `knowledge/registro_attriti.md:115`,
     già segnalato in passato). Proxy dichiarato su `alert_inviati`
     (finestra 24h, prefisso della chiave mappato a categoria leggibile).
     Copertura parziale, motivo per intero: quella tabella è un log
     "inviato una volta" senza stato aperto/risolto, e alcuni alert reali
     non ci passano mai (tetto giornaliero LLM in `connectors/llm.py`,
     contatore in-memory; notifica di job fallito generico,
     `worker/loop.py:124`; alert ad-hoc di `backend/main.py`).
  4. `osservazioni_nuove()` — `SELECT ... WHERE stato='nuova'`. Copertura
     completa; a zero righe (oggi il caso reale) nota esplicita che nessuna
     pipeline scrive ancora in `osservazioni`, non è un errore di lettura.
  5. `cantieri_aperti()` — parsing di `STATO.md`. Il file **non ha** un
     campo strutturato "cantiere: aperto/chiuso": i titoli di sessione
     mischiano data e nome cantiere in prosa libera, e (scoperta collaudando
     dal vivo) la sezione `## In corso` non è due bullet come sembra
     dall'inizio — contiene ~230 righe non delimitate (step 5-7, cantiere 2
     email, alert operativi, classificatore/drafter, depliant) perché nel
     file non c'è nessun `## ` tra quel titolo e `## Prossimi step
     (cantiere 1 — poster)`. Un parser che deducesse "quali cantieri sono
     aperti" da questa prosa sarebbe il parser fragile che il brief chiedeva
     di evitare. **Minimo indispensabile**: espone alla lettera le uniche
     due sezioni scritte con intento di stato-corrente (`In corso`,
     `DECISIONI APERTE — bloccano`) più un indice grezzo (titolo+riga) delle
     intestazioni `## `. Copertura parziale, motivo esplicito su cosa non è
     deducibile in modo affidabile.
  6. `attivita_git()` — `git log`/`git status` sulla working dir del repo.
     Copertura completa.
- **`scripts/argo/stato_cli.py`** (harness): stesso pattern di
  `scripts/panoptes/impatti.py` (script lanciato direttamente, non `-m`,
  `sys.path.insert` per importare `argo.stato`, niente `__init__.py`).
  Stampa le sei fonti in italiano con la copertura sempre in testa; `--json`
  per l'output strutturato (`json.dumps(..., default=str)` per i
  `datetime`).
- **`tests/test_argo_stato.py`** (nuovo, stile CASI del repo — niente
  pytest, mai usato altrove nel repo): un guardrail statico che legge il
  sorgente di `argo/stato.py` e verifica l'assenza di `INSERT`/`UPDATE`/
  `DELETE` (la regola "sola lettura" resa verificabile, non solo
  dichiarata) più test sulle funzioni pure di parsing (mappatura
  prefisso→categoria degli alert, estrazione sezioni di `cantieri_aperti`
  su un `STATO.md` finto). 8/8 casi passati.
- **`knowledge/mappa_sistema.yaml`**, scheda `argo_voce`: `stato` da
  `fondamenta` a `lettori`; `codice` con i due file nuovi; `tabelle.legge`
  con le sei tabelle lette (`approvals, messages, events, jobs,
  alert_inviati, osservazioni` — messages/events per via del JOIN, stesso
  motivo di `risposte_email`); `evidenza` con le note sulla deviazione
  psycopg, su `escalations` inesistente, sull'assenza di `updated_at` in
  `jobs`. **Nuovo campo `verifica.indecidibile`** (6 voci, tutte
  `tabelle.legge`): `verifica_mappa.py` cerca solo pattern `cur.execute(...)`
  e non vede nessuna delle sei tabelle, perché `argo/stato.py` non usa
  psycopg — stesso trattamento già in uso per le query-in-variabile di
  `lead_gen_host`. Rilanciato `verifica_mappa.py`: **exit 0**, 14 schede
  verificate, 0 divergenze (2 indecidibili + 8 indecidibili attesi/dichiarati,
  6 dei quali nuovi di questa sessione).

**Collaudo dal vivo (dati reali, non ipotetici) — output di
`python3 scripts/argo/stato_cli.py`:**
- `approvazioni_in_attesa`: **1** riga — approvazione `#10`, `in_attesa` da
  **174,8 ore** (~7 giorni, dal 3/9/2026), mittente Leonardo, oggetto
  "ogetto" (dato di test già presente nel DB). Copertura completa.
- `job_falliti`: 3 gruppi in `falliti` — `digest_serale` ×109 (stesso
  errore storico `thread_id::int`, 29/08, già raccontato in CLAUDE.md,
  risolto da tempo — dato morto in tabella, non un problema vivo) e
  `test_invio_dm` ×1 ×2 (401/403 da GHL/Cloudflare durante un collaudo
  manuale, non traffico reale). Zero `fermi` al momento del collaudo, uno
  al secondo (`leggi_email`, appena preso in carico — normale, il worker è
  vivo). Zero `in_coda_da_troppo`.
- `escalation_aperte`: zero alert nelle ultime 24h (l'ultimo risale al
  5/9/2026).
- `osservazioni_nuove`: zero righe, con la nota che nessuna pipeline scrive
  ancora lì.
- `cantieri_aperti`: sezioni `In corso`/`DECISIONI APERTE — bloccano`
  estratte per intero (vedi sopra sulla dimensione reale di `In corso`),
  indice di 14 intestazioni `## ` recenti.
- `attivita_git`: ultimo commit 0,26 giorni fa, 20 commit recenti, working
  tree con le modifiche in corso di questa sessione (`STATO.md`,
  `db/schema.sql`, `knowledge/mappa_sistema.yaml` modificati; `argo/`,
  `scripts/argo/`, `db/migrations/006_osservazioni_mandati.sql`,
  `knowledge/argo/` non tracciati).
- `--json` verificato: `json.loads` sull'output senza errori, sei chiavi di
  primo livello con `copertura` per ciascuna.

**Trovato collaudando, fuori scope, solo segnalato**: due job
`digest_serale` schedulati per lo stesso orario di domani
(`run_after` identico, creati a 6 secondi di distanza) — possibile corsa tra
il self-chaining del job e `garantisci_digest_serale()`. Visto per caso
validando le query di `job_falliti()`, non indagato né corretto qui
(sarebbe una scrittura, fuori dal perimetro sola-lettura di questa
sessione) — segnalato per la prossima sessione sul cantiere
email/manutenzione.

**Pre-esistente, non causato da questa sessione**: `tests/test_panoptes_lib.py`
ha un caso che fallisce (`TABELLE_NOTE` hardcoded non include
`osservazioni`/`mandati`, aggiunte dalla migrazione 006 della sessione
precedente) — 34/35 casi passati. Non toccato: appartiene al cantiere
Panoptes-Mappa, non a questo.

**Resta da fare** (prossimo cantiere): tutto quanto già elencato nella
sessione precedente (bot Telegram, connettore LLM, i tre modi
instrada/avvisa/orienta, `USER.md` popolato con l'uso) — questi sei lettori
sono l'ingrediente che mancava per iniziare quella parte, non un
sostituto. Idempotenza di `mandati` (segnalata dalla revisione guardrail
la sessione precedente) resta un prerequisito prima che Argo scriva mandati
veri — non toccata qui, questa sessione non scrive.

File toccati: `argo/stato.py` (nuovo), `scripts/argo/stato_cli.py` (nuovo),
`tests/test_argo_stato.py` (nuovo), `knowledge/mappa_sistema.yaml`, questa
sezione di `STATO.md`. Nessun commit, nessun push (lo fa Leonardo).

## Sessione 2026-09-11 — Cantiere Argo — la voce, passo 3: STATO.md leggibile + due correzioni

Prosecuzione di "la voce": `cantieri_aperti()` era quasi cieco (`## In corso`
espone alla lettera ~230 righe non sue, senza distinguere cosa è davvero
aperto). Questa sessione aggiunge un blocco strutturato e sistema due
difetti trovati collaudando la sessione precedente.

**1. Blocco `## CANTIERI`** in testa a `STATO.md`: tabella a 5 colonne
(Nome, Stato, Aperto il, Aspetta, Sessione più recente), vocabolario fisso
per Stato (`aperto|in attesa|chiuso|da confermare`) e Aspetta (`Leonardo|il
sistema|terzi|calendario|—|da confermare`). 8 cantieri ricostruiti dal
contenuto di STATO.md — dedotti con sicurezza: lead-gen host chiuso
("Roma chiuso" esplicito), Panoptes-Mappa in attesa di calendario (chiusura
prevista 17/9), Argo — la voce aperto, Designer in attesa di Leonardo
(bullet esplicito), DM Instagram/Facebook in attesa (drafter mai scritto).
Dedotti per inferenza, marcati "da confermare" dove la data di apertura non
è mai dichiarata come tale (cantiere 1, 2, 3, Designer): uso la prima
traccia disponibile solo come nota, mai come fatto certo. "Cantiere 2 —
email" marcato `aperto` perché CLAUDE.md lo dichiara cantiere attivo, non
perché esista una sessione recente a lui dedicata. Regista Sonora v10
incluso "da confermare" su tutto: citato in STATO.md solo come motivo di due
deroghe, mai col suo contenuto — incluso comunque perché il modo *orienta*
di Argo non deve sembrare ignorarlo.

**2. Delimitata `## In corso`**: mancava un `## ` prima di `## Prossimi step
(cantiere 1 — poster)`, quindi la sezione inghiottiva le note di step 5-7
del poster e l'intero cantiere 2 — email. Aggiunta l'intestazione
`## Dettaglio implementativo (poster step 5-7 e cantiere 2 — email)` subito
dopo le due righe vere di "In corso" — nessuna parola di contenuto toccata.

**3. `argo/stato.py` — `cantieri_aperti()` legge il blocco**: nuovo helper
puro `_estrai_cantieri(testo)`, parsing della tabella markdown con
validazione delle intestazioni e del vocabolario di Stato/Aspetta. Copertura
`completa` quando il blocco è presente e ben formato, `parziale` con motivo
esplicito altrimenti (blocco assente, intestazioni sbagliate, riga fuori
vocabolario) — mai un dato parziale spacciato per completo. `in_corso`/
`decisioni_aperte_bloccano`/`sessioni_recenti` restano sempre esposti alla
lettera, non solo come fallback silenzioso. `scripts/argo/stato_cli.py`
aggiornato per stampare la nuova sezione "cantieri (blocco strutturato)".
Bug trovato in fase di collaudo e corretto prima di chiudere: la prima
implementazione della validazione di `Aspetta` prendeva solo la prima
parola della cella (`aspetta.split(" ")[0]`), quindi "il sistema" falliva
sempre (matchava solo "il"). Corretto per matchare il token canonico più
lungo che apre la cella. 5 nuovi casi in `tests/test_argo_stato.py`
(blocco ben formato, assente, intestazioni sbagliate, stato fuori
vocabolario, `cantieri_aperti()` end-to-end completa/parziale) — 19/19.

**4. `CLAUDE.md`**: una riga sotto "Stato del progetto" — il blocco
`## CANTIERI` va aggiornato a fine sessione insieme alla nota, è la fonte
primaria di `cantieri_aperti()`.

**Correzione — corsa `digest_serale`** (segnalata dalla sessione
precedente): causa isolata. Le tre `garantisci_*` (`leggi_email`,
`controlli_periodici`, `digest_serale`, `worker/loop.py`) fanno un
check-poi-insert non atomico (`SELECT ... IN ('pending','running')`, poi
`INSERT` se vuoto). Nel loop seriale di un worker questo non corre mai con
se stesso: corre solo se due processi worker esistono per una finestra
breve (es. durante un `docker compose up -d --build`) **e** in quel momento
non esiste ancora nessuna riga pending/running — il caso esatto che la
funzione recupera. `prossimo_orario_digest()` è deterministico sulla data,
quindi due inserimenti quasi simultanei producono lo stesso `run_after`:
esattamente il sintomo osservato (due job digest_serale, stesso orario,
creati a 6 secondi di distanza). Il self-chaining dentro `digest_serale()`
non è la causa (insert incondizionato, il job corrente è già `running`
quando esegue). Fix: `pg_advisory_xact_lock` (chiave propria per funzione)
in testa a ciascuna delle tre `garantisci_*`, prima della SELECT — nessuna
migrazione, nessun rischio per il self-chaining esistente. Corrette tutte e
tre (non solo digest_serale): il vincolo del brief era contro modifiche
larghe, non contro tre righe della stessa natura, e lasciarle rotte sapendo
perché sarebbe stato peggio che toccarle. `knowledge/mappa_sistema.yaml`
aggiornata (righe shiftate in `manutenzione_sistema`: `codice`, MS02/MS03/
MS04 `garantito_da`, evidenza — nuovo limite superiore file 1660, era 1647)
e rilanciato `verifica_mappa.py`: exit 0.

**Correzione — `tests/test_panoptes_lib.py`**: `TABELLE_NOTE` non includeva
`osservazioni`/`mandati` (migrazione 006). Aggiunte, stringa descrittiva del
caso corretta ("le 8" → "le 10 tabelle note"). 35/35.

**`knowledge/registro_attriti.md`**: aggiunta voce A26 (seed, non
misurata) su richiesta di Leonardo — la memoria di Argo tra sessioni è oggi
solo `STATO.md` + i file identità, da rivalutare con evidenza d'uso dopo
alcune settimane, candidato per il radar skill/tool.

**Verifiche finali**: `test_argo_stato.py` 19/19, `test_panoptes_lib.py`
35/35, `test_fetch.py` 12/12, `test_filtri_email.py` 25/25,
`test_normalizza.py` 132/132 (`eval_classificatore.py` escluso, a
pagamento); `verifica_mappa.py` exit 0; `stato_cli.py` →
`cantieri_aperti` copertura completa, 8 cantieri.

File toccati: `STATO.md` (blocco CANTIERI, delimitatore In corso, questa
sezione), `argo/stato.py` (`_estrai_cantieri`, `cantieri_aperti()`),
`scripts/argo/stato_cli.py`, `tests/test_argo_stato.py`,
`tests/test_panoptes_lib.py`, `worker/loop.py` (tre `garantisci_*`),
`knowledge/mappa_sistema.yaml`, `CLAUDE.md`, `knowledge/registro_attriti.md`.
Nessun commit, nessun push (lo fa Leonardo).

## Sessione 2026-09-11 — Cantiere Argo — la voce, passo 4: modo "orienta"

Primo comportamento reale del cantiere e prima chiamata LLM: `argo/voce.py`
(`genera_risposta()`) raccoglie le sei fonti di `argo/stato.py`, costruisce
il system prompt da `knowledge/argo/{SOUL,IDENTITY,USER}.md` (letti dai
file, non duplicati) + istruzioni comportamentali esplicite (poche righe,
mai un elenco totale, tu, conclusione prima, una sola prossima cosa con
motivo, dichiara le fonti a copertura parziale/assente, silenzio è un esito
normale, niente incoraggiamenti/riassunti/percentuali) + stato serializzato
in JSON, chiama `connectors/llm.py:chiama()` (Haiku, temperatura 0 — già il
default). `scripts/argo/orienta.py` lancia tutto a mano da host e manda il
testo sul bot Telegram nuovo (`ARGO_VOCE_BOT_TOKEN`). Nessuna scrittura sul
DB, nessun polling/webhook/scheduler, come richiesto — il bot meccanico
esistente non è stato toccato in alcun modo.

**Connettore Telegram esteso, non duplicato**: `connectors/telegram.py:notifica()`
ha ora un parametro opzionale `token=None` (`token or
os.environ.get("TELEGRAM_TOKEN")`) — stesso pattern già in uso in
`connectors/mailer.py` per mittente/password parametrici. Tutte le chiamate
esistenti (`notifica(testo)`, worker/loop.py, backend/main.py,
connectors/llm.py, backup/invia_backup.py, scripts/risolvi.py) restano
identiche; solo `orienta.py` passa `token=ARGO_VOCE_BOT_TOKEN`, stesso
`TELEGRAM_CHAT_ID` del bot meccanico.

**Chiarimento di scope su un invariante, prima di scrivere codice**: il
sub-agent `guardrail-review` ha segnalato un punto reale — l'invariante
CLAUDE.md "nessun invio automatico di messaggi redatti da un LLM: tutto
passa da approvals" non aveva un'eccezione esplicita per il traffico
interno, a differenza dell'invariante gemello su `messages` (che eccettua
le email operative verso l'operatore). Il messaggio "orienta" è generato da
un LLM e va a Leonardo senza passare da `approvals`. Chiesto a Leonardo
invece di assumere: confermato che l'invariante approvals è scoped ai
messaggi verso host/prospect (un'approvazione di Leonardo su un messaggio
diretto a Leonardo sarebbe circolare — lui è già il destinatario). CLAUDE.md
corretto per renderlo esplicito ("verso host o prospect" + una riga di
eccezione dedicata ai messaggi di Argo a Leonardo), stessa logica già usata
per l'eccezione su `messages`.

**Costo reale, misurato non solo stimato**: il piano stimava 5.500-6.000
token di system prompt (dominati da `DECISIONI APERTE — bloccano`, non dai
file identità). Il lancio vero ha loggato **11.485 token in ingresso**, quasi
il doppio. Causa più probabile: `json.dumps(..., indent=2)` raddoppia/
triplica il peso in caratteri di testo libero (virgolette, `\n` escapati,
indentazione) rispetto al conteggio a occhio sul testo grezzo di STATO.md —
non misurato riga per riga in questa sessione, solo osservato sul totale.
342 token in uscita (tetto `max_tokens=400`). Costo assoluto comunque
trascurabile su Haiku per un comando lanciato a mano; se "orienta" diventa
un canale sempre acceso, primo candidato da tagliare è la serializzazione
JSON indentata dello stato, non i file identità.

**Testo generato dal collaudo reale (11/9/2026, ~11:05)**, incollato senza
modifiche:

> Sei in tre cantieri contemporaneamente, uno dei quali blocca gli altri due.
>
> **Il blocco:** Cantiere Designer, Fase C. Hai rimosso il fix superfluo ieri
> (11/9, commit `01e4b5959`), ma non hai ancora reincollato i blocchi
> corretti sulla pagina di prova GHL. Finché non lo fai, non puoi misurare
> l'anti-finestra-morta sull'anteprima reale — e quella misura è il gate per
> chiudere il cantiere.
>
> **Prossima cosa:** Accedi a GHL, incolla i tre blocchi corretti
> (`blocco_01.html`, `blocco_hero_mobile_v3.html`, e il footer se decidi di
> toccarlo) sulla pagina di prova, poi ripeti il test di pavimento +
> finestra-morta a 375/767/768/861/1024px sull'anteprima reale. Se passa, il
> cantiere chiude.
>
> Dietro quel gate stanno aspettando:
> - Cantiere Panoptes-Mappa (chiusura prevista 17/9, oggi è il 12).
> - Cantiere Argo (due correzioni minori a STATO.md, poi pronto).
>
> I job falliti (digest_serale, 109 volte) sono rumore — errore SQL noto,
> non blocca nulla.

**Due errori fattuali osservati nel testo, non corretti nel codice** (segnalo
invece di far finta di non vederli — proprietà di un output LLM, non un bug
di `argo/voce.py`): la data è sbagliata ("oggi è il 12", oggi è l'11/9/2026)
e l'hash di commit ha una cifra di troppo (`01e4b5959` invece di `01e4b59`,
quello vero in `git log`). Nessuno dei due è nello stato passato al modello
(entrambi corretti nel JSON): sono invenzioni del modello sopra dati esatti,
non un difetto della raccolta stato. Segnalo qui perché rientra proprio nel
giudizio "il carattere è giusto o va corretto" che questa sessione doveva
raccogliere — un candidato concreto per instruire esplicitamente il prompt a
non calcolare/riscrivere date o hash, riportarli solo se già presenti
letteralmente nello stato.

**Nessun ascolto proposto**: come da richiesta, nessun polling/webhook/
scheduler aggiunto — resta un comando a mano finché Leonardo non decide se
"orienta" merita un canale sempre acceso.

**Verifiche finali**: `tests/test_argo_voce.py` 16/16 (nuovo — guardrail
statico nessuna scrittura SQL + verifica che il system prompt contenga
davvero i tre file identità/istruzioni/stato), `tests/test_argo_stato.py`
19/19 (nessuna regressione), `test_fetch.py`/`test_filtri_email.py`/
`test_normalizza.py`/`test_panoptes_lib.py` verdi; `verifica_mappa.py` exit
0 (14 schede, 0 divergenze); sub-agent `guardrail-review` sul diff completo
prima del collaudo — nessuna violazione netta, un solo punto ambiguo
(approvals, risolto sopra).

File toccati: `argo/voce.py` (nuovo), `scripts/argo/orienta.py` (nuovo),
`tests/test_argo_voce.py` (nuovo), `connectors/telegram.py` (`notifica()`
parametrica su `token`), `knowledge/mappa_sistema.yaml` (scheda `argo_voce`:
stato, nota_stato, attivazione, produce, codice, env, condivisi, esterni,
contratto AV03; scheda condivisa `telegram_notifica`: `usato_da` +
evidenza), `CLAUDE.md` (scope dell'invariante approvals), `STATO.md`
(blocco CANTIERI, questa sezione). Nessun commit, nessun push (lo fa
Leonardo). Aspetta: Leonardo legge il testo sopra e giudica se il carattere
è giusto o va corretto in `knowledge/argo/{SOUL,IDENTITY,USER}.md`.

## Sessione 2026-09-11 — Cantiere Argo — la voce, correzioni post-collaudo

Il primo collaudo reale (sessione precedente, stesso giorno) ha mostrato tre
problemi: due invenzioni fattuali su dati che il modello aveva davanti
(data sbagliata, hash del commit con una cifra in più), verbosità oltre il
richiesto (una sezione "dietro quel gate stanno aspettando" più una nota sui
job falliti, non richieste), e un costo quasi doppio della stima per via del
`json.dumps` indentato. Tre correzioni mirate, decise da Leonardo dopo aver
letto il testo — priorità alla prima: un agente che inventa dettagli
plausibili su dati che ha davanti non è usabile.

**1. Regola anti-invenzione, in tre punti**:
- `knowledge/argo/SOUL.md`, sotto "Il tratto fondamentale": date, hash,
  numeri, nomi di file e ID si riportano solo se presenti alla lettera nello
  stato ricevuto, copiati senza modifiche; se un dettaglio non c'è, si omette
  la frase, mai ricostruirlo a memoria o per plausibilità.
- `argo/voce.py:ISTRUZIONI_ORIENTA`: stessa regola in forma operativa,
  esplicitamente collegata al campo `"oggi"` (vedi sotto) come unico posto
  dove trovare la data.
- `argo/voce.py:raccogli_stato()`: nuovo campo `"oggi"` (data odierna, fuso
  Europe/Rome via `_data_oggi()`, formato ISO `YYYY-MM-DD`) — l'unico dei due
  errori del primo collaudo causato da un dato davvero mancante, non da
  un'invenzione pura: ora non c'è nulla da calcolare.

**2. Verbosità**: `ISTRUZIONI_ORIENTA` rinforzata — "una sola prossima cosa,
col motivo, poi FERMATI: niente sezioni aggiuntive, niente elenco di
cos'altro aspetta, niente nota a parte sui job falliti a meno che sia
proprio quella la scelta". `MAX_TOKENS_RISPOSTA` 400 → 200 (backstop, non il
meccanismo primario).

**3. Costo — stima poi verificata**: `costruisci_system_prompt()` ora
serializza lo stato con `json.dumps(..., separators=(",", ":"))` (compatto,
non `indent=2`) e tronca `decisioni_aperte_bloccano` oltre
`LIMITE_DECISIONI_APERTE_CARATTERI = 3000` caratteri (era 11.166 caratteri
reali, la voce singola più pesante del prompt) con una nota esplicita nel
testo passato al modello ("[TRONCATO — N caratteri totali, testo completo in
STATO.md]"). Il troncamento avviene su una copia dentro
`_stato_per_prompt()` (`copy.deepcopy`): `argo/stato.py` e chi lo consuma
per un umano (`scripts/argo/stato_cli.py`) restano fedeli e completi, non
tagliati. Stima nel piano, prima di implementare: ricostruito il system
prompt reale del primo collaudo (31.353 caratteri → 11.485 token misurati,
rapporto 0,366 token/carattere) e simulata la versione nuova →
~21.400 caratteri stimati, **~7.800 token attesi**. Rilanciato
`scripts/argo/orienta.py` per verificare: **7.787 token in ingresso reali**
— stima confermata quasi esatta, -32% rispetto agli 11.485 originali.

**Testo del secondo collaudo (11/9/2026, ~11:18)**, incollato senza
modifiche:

> Sei nel cantiere Argo — la voce, passo 4: il modo "orienta" che hai appena
> collaudato su Telegram è pronto, e aspetta il tuo giudizio sul carattere
> (SOUL.md, IDENTITY.md, USER.md).
>
> Hai tre file modificati non committati (`argo/voce.py`, `SOUL.md`,
> `tests/test_argo_voce.py`). La prossima cosa è decidere se il carattere
> che hai scritto regge, oppure se serve una correzione prima di
> committare.

138 token in uscita (tetto 200), una sola prossima cosa, nessuna sezione
extra. I tre file citati corrispondono esattamente a `git status` al
momento del lancio — nessuna data, hash o nome inventato: la regola
anti-invenzione non è ancora stata messa alla prova su un caso con dati
mancanti veri (in questo stato, alla portata del modello c'era tutto quello
che ha detto), ma il collaudo minimo (niente di inventato su dati presenti)
è passato.

**Verifiche finali**: `tests/test_argo_voce.py` 26/26 (10 casi nuovi:
regola anti-invenzione in `ISTRUZIONI_ORIENTA` e in SOUL.md, `_data_oggi()`
formato ISO, `_stato_per_prompt()` tronca sopra soglia con nota e lascia
intatto sotto soglia senza modificare l'originale, `raccogli_stato()`
include `"oggi"`), `tests/test_argo_stato.py` 19/19 (nessuna regressione).
`verifica_mappa.py` non rilanciato in questa sotto-sessione: nessun cambio a
tabelle/env/confini di pipeline, solo `nota_stato` (testuale, non
verificato dallo script).

File toccati: `knowledge/argo/SOUL.md` (regola anti-invenzione),
`argo/voce.py` (istruzioni rinforzate, campo `oggi`, `_data_oggi()`,
`_stato_per_prompt()`, `MAX_TOKENS_RISPOSTA` 200), `tests/test_argo_voce.py`
(10 casi nuovi), `knowledge/mappa_sistema.yaml` (nota_stato di `argo_voce`),
`STATO.md` (questa sezione). Nessun commit, nessun push in questa
sotto-sessione (richiesto esplicitamente da Leonardo): li fa lui dopo aver
letto il testo sopra.
