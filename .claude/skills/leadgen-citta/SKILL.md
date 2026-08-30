---
name: leadgen-citta
description: Ripete l'intero processo di lead-gen host (raccolta Google Places, resolver contacts/identities, export punteggiato) per aprire una nuova città, replicando esattamente i passi, i comandi e le decisioni prese per Roma il 30/08. Usala quando si apre una nuova città per il cantiere lead-gen host.
---

# Lead-gen host — aprire una nuova città

## 1. Precondizione di business

Si parte solo se Narratours ha già tour attivi per quella città. Senza tour
attivi la raccolta produce magazzino: contatti che non si possono lavorare
finché non c'è un'offerta reale da proporre loro. Verificare PRIMA di
aprire una cella, non dopo.

## 2. Prerequisiti tecnici — già fatti una volta per tutte, non per città

- `PLACES_API_KEY` in `/root/argo/.env` (mai committata — CLAUDE.md). Una
  sola chiave per tutte le città: non crearne una nuova per ogni città.
- Restrizioni già configurate su Google Cloud Console (Places API (New)
  abilitata, il resto disattivato) — non toccare per aprire una città nuova.
- Tier gratuito: **1.000 chiamate/mese, condiviso tra tutte le città** — non
  si resetta per città. Roma ha usato ~223 chiamate in un mese (128 raccolta
  reale + ~95 dry-run): controllare quante ne restano nel mese di calendario
  corrente prima di aprire una città nuova nello stesso mese.
- Infrastruttura Docker già pronta, non richiede altro setup:
  `Dockerfile` copia `scripts/`, `docker-compose.yml` monta
  `./out/places:/app/dati/places` e `./out/export:/app/dati/export` sul
  worker, migrazione `db/migrations/005_prospect.sql` già applicata
  (`contacts.telefono/sito/indirizzo/fonte/fonte_dettaglio/attributi`,
  tabella `soppressioni`).

## 3. Passi, nell'ordine reale, con i comandi esatti

1. **Celle**: aggiungere le nuove celle a `CELLE` in
   `scripts/cerca_places.py` (rettangoli lat/lng — prima passata su base
   OpenStreetMap/confini di quartiere noti, non serve precisione al primo
   colpo, si aggiusta dal dry-run).

2. **Dry-run** (gira sull'host, fuori Docker — richiede `PLACES_API_KEY` in
   `.env`, letta da `carica_env()`):
   ```
   python3 scripts/cerca_places.py --dry-run
   ```
   `--dry-run` oggi è cablato sulle 3 celle di prova di Roma
   (`CELLE_DRY_RUN`) — per una città nuova aggiornare quella costante o
   usare `--celle <nomi>` con le celle di prova della città nuova. **Leggere
   l'output prima di procedere** (checkpoint umano, sezione 4).

3. **Raccolta reale, cella per cella, MAI `--celle tutte`**:
   ```
   python3 scripts/cerca_places.py --celle <nome_cella> --max-chiamate 150
   ```
   una volta per cella, in sequenza: un problema su una cella non fa
   perdere le altre. Ogni cella scrive il proprio
   `out/places/places_<timestamp UTC>.jsonl`, mai sovrascritto.

   **Riferimento Roma** (5 celle): 128 chiamate API totali, 2003 schede
   grezze. Uno scostamento forte da questi ordini di grandezza a parità di
   densità urbana (es. molte più chiamate o poche decine di schede) è
   un'anomalia — cella troppo grande/piccola o mal piazzata.

4. **Migrazione e volumi**: già fatti una volta per tutte (sezione 2), non
   ripetere per una città nuova a meno che lo schema cambi.

5. **Resolver, un file alla volta, in sequenza, con `--fonte-dettaglio` e
   `--citta`**:
   ```
   docker compose exec worker python -m scripts.risolvi \
     --fonte-dettaglio <cella> --citta <citta> /app/dati/places/<file>.jsonl
   ```
   `--citta` è obbligatorio da questo commit — nome città in minuscolo,
   stesso stile di `--fonte-dettaglio` (`"milano"`, non `"Milano"`).

   **Riferimento Roma**: 22 schede scartate dal filtro (su 2003), 1197
   contatti prospect, 58 con più di una struttura, 7 con 4 o più strutture.

6. **Test di idempotenza — non facoltativo**: rilanciare l'ULTIMO file
   appena processato con GLI STESSI argomenti. Deve dare 0 contatti nuovi, 0
   identità agganciate. Se non è zero, fermarsi e capire perché prima di
   processare altre città — è la garanzia che un rilancio dopo un errore non
   duplica nulla.

7. **Export**:
   ```
   docker compose exec worker python -m scripts.export_prospect [--limite N] [--solo-con-telefono]
   ```
   CSV in `out/export/prospect_<timestamp UTC>.csv` sull'host.

## 4. Checkpoint che restano umani, e perché

- **Leggere il dry-run prima di scrivere**: i conteggi (schede/ammesse/
  scartate/con telefono/con sito) sono l'unico modo di accorgersi che una
  cella è mal piazzata prima di spendere le chiamate reali — le coordinate
  non hanno una verifica automatica.
- **"Domini da valutare" a fine resolver**: `risolvi.py` stampa i 10 domini
  più condivisi ancora sotto soglia. È l'unico modo di scoprire la prossima
  piattaforma di booking non ancora in `AGGREGATORI` prima che inquini un
  batch — su Roma ne sono spuntate 8 al primo giro (krossbooking, spacest,
  vio, freecancellations, snaptrip, bluepillow, voyabay, trip.com).
  Leggerla ad ogni run, non solo la prima volta.
- **Top 15 dell'export**: deve avere i multi-struttura in cima e gli
  ostelli sparsi in mezzo, non ammucchiati in testa solo per tipo. Se la top
  15 assomiglia a "quasi solo ostelli/hotel", i pesi sono da rivedere — è
  già successo su Roma, corretto il 30/08 (sezione 5). Non fidarsi del
  punteggio senza guardare la lista.

## 5. Decisioni già prese — non riaprirle senza un motivo nuovo

- **Soglia di condivisione domini = 8** (`DOMINIO_MAX_STRUTTURE_CONDIVISE`
  in `connectors/normalizza.py`): una blocklist statica (`AGGREGATORI`) non
  basta da sola perché i booking engine/OTA nuovi spuntano di continuo — si
  scoprono solo dopo aver già fuso decine di strutture non correlate in un
  falso "gestore". 8 è il valore più basso che non taglia i gestori piccoli
  ma reali (misurati su Roma nel range 4-6 strutture) pur intercettando
  tutto ciò che era ambiguo: sopra 8 e sopra 12 davano lo stesso risultato
  (nessun dominio nel range 9-12) — 8 è la soglia più stretta possibile
  senza perdere segnale vero.
- **Pesi del punteggio, impresa = 15 non 30** (`scripts/export_prospect.py`):
  con 30 punti fissi per tipo-impresa e un bonus fisso di 25 per
  `n_strutture>1`, un singolo ostello con tante recensioni batteva un
  gestore vero con 4-6 strutture — misurato su Roma: i 7 contatti con 4+
  strutture erano in posizione 48-112 su 1197. Ritarato il 30/08: impresa
  30→15, `n_strutture` da bonus fisso a scala (2→20, 3→30, 4→40, 5+→50,
  senza tetto perché la soglia sui domini ha già tolto le piattaforme
  false).
- **JSONL grezzi fuori dal repo** (`out/` in `.gitignore`, mai committati):
  hanno permesso due ricostruzioni complete del DB (DELETE + re-risoluzione)
  a costo zero di chiamate API, quando sono stati scoperti prima il bug
  delle fusioni sui booking engine e poi trip.com — senza i grezzi salvati,
  ogni correzione al filtro avrebbe richiesto ri-raccogliere da Google,
  pagando di nuovo.

## 6. Regola di stop

Si smette di raccogliere celle quando i contatti prodotti superano di **tre
volte** la capacità reale di contatto (quante chiamate/email il team riesce
davvero a fare in un tempo ragionevole) — non quando le celle configurate
sono finite. Aprire tutte le celle di una città e basta produce magazzino
che nessuno lavorerà mai, esattamente come una città senza tour attivi
(sezione 1).

## 7. Cosa cambia da città a città, cosa no

**Cambia solo**:
- Le coordinate delle celle (`CELLE` in `scripts/cerca_places.py`).
- Fuori dall'Italia, le parole chiave di ricerca (`RICERCHE` — oggi "bed and
  breakfast", "affittacamere e guest house", "ostello", "casa vacanze":
  stringhe in italiano, da tradurre nella lingua locale perché Places Text
  Search cerca sul testo).

**Non cambia**: filtro tipi/stato, regole di normalizzazione
(`connectors/normalizza.py`), soglia domini, pesi del punteggio, tutta la
logica di `risolvi.py`.

**Da non fare, mai**:
- Scraping Airbnb: gli aggregatori (Airbnb incluso) sono esclusi apposta
  dall'identità — nessun motivo di andarli a raschiare.
- DM a freddo: questa è una lista per chiamate/email dirette da un umano,
  non per invio massivo automatico — coerente con l'invariante generale del
  progetto (CLAUDE.md, nessun invio automatico senza approvazione o
  criterio esplicito).
- Committare `out/places/*.jsonl` o `out/export/*.csv`: dati di contatto
  reali, restano solo sul VPS (`.gitignore`), mai nel repo.
