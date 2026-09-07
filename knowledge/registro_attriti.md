# REGISTRO DEGLI ATTRITI — v0

**7 settembre 2026 — Cantiere Skill & Tool, artefatto 1 di 2**
Posizione prevista nel repo: `knowledge/registro_attriti.md`

**Cos'è:** una riga per ogni cosa che è costata tempo o è stata corretta a mano
nei cantieri, con un numero accanto. È l'archivio di fatti reali di questo
cantiere — l'equivalente dei 41 montaggi della Regia sonora.

**La regola:** un attrito senza numero non giustifica l'installazione di niente.
"A volte è scomodo" non è un attrito; "otto volte in due cantieri, dieci minuti
l'una" sì.

---

## Formato

```
ID:        A + numero progressivo
Attrito:   cosa succedeva, in una riga concreta
Contesto:  cantiere o attività dove succede
Volte:     quante volte è successo (numero, non "spesso")
Costo:     tempo o danno per occorrenza
Stato:     aperto | chiuso | accettato (deliberatamente non risolto)
Candidati: id dall'indice_candidati che lo toccano (vuoto se nessuno)
```

---

## Attriti registrati

*Popolato all'indietro il 7/09 dai cantieri chiusi (poster, lead-gen Roma, email
IMAP, risposte email, DM IG/FB). Fonti: DB live (sola `SELECT`), git log,
STATO.md. Ordinate per Volte decrescente; dove Volte è "?" è un rischio noto/
accettato citato in STATO.md, non un incidente contato.*

| ID | Attrito | Contesto | Volte | Costo/volta | Stato | Candidati |
|---|---|---|---|---|---|---|
| A07 | `thread_id` reso alfanumerico ha rotto le query `::int` nel digest serale (errore `invalid input syntax for type integer: "1468:depliant"`) | Digest serale (cross-cantiere: poster/depliant + email) | 109 (jobs.tipo='digest_serale', stato='failed', 28-29/08; verificato nel codice attuale: nessun `thread_id::int` residuo, solo `event_id::int` in worker/loop.py:673 → chiuso) | ? | chiuso | 92 Code Review (debole) |
| A08 | Contatti con email-placeholder scritta prima della regola generale, ripuliti a mano (6 recuperati, 2 rimasti vuoti) | Lead-gen Roma (estrazione email) | 8 (commit `57273db`) | ? | chiuso | |
| A09 | Alert Telegram IMAP senza dedup: una casella down genera un flood di messaggi ("centinaia", numero esatto non nel commit) | Cantiere 2 (email IMAP) | 1 incidente noto (frequenza reale prima del fix sconosciuta) | ? | chiuso (fix 04/09, commit `1941229`) | |
| A10 | Bug di estrazione URL Facebook: troncamento `/pages`, `/people`, `/pages/category`; slug numerico `/1278` trattato come pagina vera | Lead-gen Roma (estrazione social) | 2 bug distinti (STATO.md:124-129, 145-156; commit `2f118fe`) | ? | chiuso | 86 Scrapling (debole) |
| A11 | Collaudo drafter/filtro warmup: tono non conforme (lei/tu poi lei/voi) + filtro warmup non strutturale — 3 correzioni lo stesso giorno prima del deploy | Cantiere risposte email | 3 (commit `674bf7f`, `eea9796`, `7c49c5b`, tutti 03/09) | ? | chiuso — costo di collaudo | |
| A12 | Approvazioni corrette dall'operatore prima di approvare (stato `modificata`) | Cantiere risposte email | 2 (approvals.stato='modificata') | ? | accettato — è lo scopo del gate, non un difetto | |
| A13 | Approvazioni ferme in `in_attesa` da oltre 24h senza `scadenza` impostata | Cantiere risposte email | 2 (id 4 dal 23/08, id 10 dal 03/09) | ? | aperto — conferma il seed A02 con un numero | |
| A14 | Job `test_invio_dm` falliti: collaudo manuale che sostituisce il drafter DM mai scritto | Cantiere 3 (DM IG/FB) | 2 (jobs.tipo='test_invio_dm', stato='failed') | ? | aperto — drafter DM ancora mancante (STATO.md) | |
| A15 | Sotto-quadrante Places saturo anche a bisezione massima (`prati_borgo#q0#q3`) | Lead-gen Roma (raccolta Places) | 1 | ? | accettato (STATO.md:19-22) | |
| A24 | Filtro warmup Instantly assente sul connettore IMAP: email di warmup non filtrate, osservato sui log prima del fix | Cantiere 2 (email IMAP) | 1 (fix, commit `d95d894`, 27/08 — confermato dall'operatore: problema già osservato sui log) | ? | chiuso | |
| A25 | Script export lead-gen "ad hoc" andava sistemato a mano a ogni export (problemi con X, non specificato) | Lead-gen Roma (export Instantly) | ? — vedi SOSPESO 11 | ? | chiuso (sostituito da `scripts/export_instantly.py`, commit `87dcfab`) | |
| A16 | Tetto giornaliero LLM in-memory: si azzera a ogni riavvio worker | Cantiere risposte email | ? | ? | aperto (STATO.md:511-516) | |
| A17 | Classificazione/bozza fallita non viene mai ritentata (guardia idempotenza scritta prima) | Cantiere risposte email | ? | ? | accettato — trade-off scelto (STATO.md:517-523) | |
| A18 | Guardia idempotenza scritta prima dell'invio: rischio messaggio registrato ma mai partito | tutti i canali (email/DM) | ? | ? | aperto (STATO.md:530-540) | |
| A19 | Identity resolution non implementata: `contacts`/`identities` mai popolate, `contact_id` sempre NULL | tutti i canali | ? | ? | aperto (STATO.md:541-546) | |
| A20 | `IMAP_HOST` globale: caselle `.click` non possono rientrare in lettura con host dedicato | Cantiere 2 (email IMAP) | ? | ? | aperto (STATO.md:553-556) | |
| A21 | Rimbalzo email senza `delivery-status` parsabile trattato come temporaneo | Cantiere risposte email | ? | ? | accettato (STATO.md:273-277) | |
| A22 | `reply_channel` statico nel workflow GHL: rischio etichetta IG/FB errata senza errore visibile | Cantiere 3 (DM IG/FB) | ? | ? | aperto (STATO.md:446-448) | |
| A23 | `dedup_key` DM basata su `triggered_at` grezzo, non su un id univoco messaggio | Cantiere 3 (DM IG/FB) | ? | ? | aperto (STATO.md:459-466) | |

Accoppiamento corsia riparazioni fatto il 07/09 in chat di progetto: 5 match
su 25 attriti, ~35 candidati su 41 senza attrito. Corsia evoluzioni: primo
giro manuale previsto dopo l'import della baseline 65.

Nota sul seed sotto: **A02** è confermato e superato da A13 (ora ha un numero
reale). **A04** è coperto dalle righe A07-A14 sopra (correzioni manuali contate
per poster/IMAP/DM/leadgen/risposte). Le righe A01-A06 restano invariate sotto
per riferimento; le domande su come chiuderle sono in SOSPESI.

---

## SOSPESI

1. [RISOLTO 07/09] Cantiere 2 (IMAP) e "cantiere risposte" non hanno mai un
   commit/nota di chiusura esplicita in STATO.md, e CLAUDE.md dichiara ancora
   "Cantiere attivo: 2 — email" mentre STATO.md descrive il secondo pezzo
   (classificazione LLM + bozze) come "collegato al traffico vero". Vanno
   considerati chiusi ai fini del registro (come ho fatto sopra, A11-A23) o
   esclusi perché ancora attivi?
   **Risposta:** restano chiuse ai fini del registro: sono attive ma stabili,
   in produzione.
2. [RISOLTO 07/09] Commit `d95d894` ("Filtro warmup Instantly sul connettore
   IMAP", 27/08) è un fix di un difetto reale osservato o una feature nuova?
   Se fix, va aggiunto come attrito (Volte=1).
   **Risposta:** è un fix, il warmup Instantly era già osservato sui log.
   → aggiunto come A24 in "Attriti registrati".
3. [RISOLTO 07/09] Commit `87dcfab` ("scripts/export_instantly.py", 31/08)
   sostituisce uno script "ad hoc" del cantiere lead-gen già chiuso: conta come
   costo evitato, o è normale iterazione di feature (esclusa)?
   **Risposta:** è un attrito — lo script vecchio andava sistemato a mano a
   ogni export / aveva dato problemi con X (dettaglio non specificato).
   → aggiunto come A25 in "Attriti registrati"; Volte e "X" restano SOSPESI
   (vedi SOSPESO 11).
4. Il flood di alert Telegram (A09) è documentato come "centinaia di messaggi"
   senza numero esatto, un solo incidente noto. Quante volte si è già
   verificato prima del fix del 04/09? Non esiste uno storico Telegram
   consultabile in questa sessione — dove si troverebbe (export chat, log bot)?
5. [RISOLTO 07/09] I tre fix di collaudo del drafter (A11, tutti 03/09, stesso
   giorno del deploy) sono correzioni pre-produzione, non guasti in
   produzione. Li conto come attrito (costo del collaudo) o li escludo perché
   "il collaudo ha funzionato come doveva"?
   **Risposta:** contali come attrito, costo di collaudo, stato chiuso. Se il
   pattern "fix nel giorno del deploy" ricorre su altri cantieri, è un
   attrito ricorrente tra cantieri. → vedi nuovo SOSPESO 12.
6. A01, A05 (Regia sonora/Regista): girano su PC Windows, fuori perimetro di
   questa sessione — da contare sul PC, nessun dato qui.
7. A03 (setup ripetuto ad ogni sessione Claude Code): vale anche per le sessioni
   su Argo, non solo Regia sonora? Se sì, quale passaggio manuale esatto
   (quale file/comando) intendi?
8. A06 (verifica manuale stato tool/modelli, "quasi quotidiana"): è un attrito
   del processo di progettazione di questo stesso cantiere, non riconducibile a
   un commit/log nel repo Argo. Con quale evidenza lo conteresti?
9. Le 109 righe `jobs` fallite di A07 sono storico morto in tabella (mai
   ripulito, mai ritentato dopo il fix). In una prossima sessione operativa
   (non questa, sola lettura) vuoi che vengano cancellate/riaccodate, o restano
   così?
10. `escalations` (citata nella richiesta originale) non esiste nello schema:
    né nei file SQL, né nel DB live, né nel codice. Va creata in futuro, o la
    funzione più vicina (`alert_inviati` + `approvals.stato` + `jobs.stato`)
    basta così com'è?
11. A25: quante volte lo script vecchio è stato sistemato a mano prima di
    essere sostituito (quanti export)? E qual è "X" — quale problema specifico
    dava? Servono per completare Volte e la descrizione di A25.
12. Il pattern di A11 ("fix il giorno stesso del deploy") ricorre in altri
    cantieri oltre a "risposte email"? Non ancora verificato in questa sessione
    — richiederebbe di incrociare, per ogni cantiere, la data dei commit di
    chiusura/deploy con eventuali fix associati allo stesso giorno. Se ricorre,
    diventa un attrito trasversale (es. "il collaudo del giorno stesso del
    deploy trova sempre N correzioni") da aggiungere come riga a sé.

---

## Seed — candidati attriti da confermare

Questi vengono dalla storia documentata dei cantieri. **I numeri li metti tu**:
finché non hanno Volte e Costo, non sono attriti, sono ricordi. Cancella quelli
che non reggono il conteggio.

| ID | Attrito candidato | Contesto | Volte | Costo/volta | Stato |
|---|---|---|---|---|---|
| A01 | Sessione Claude Code bloccata da permessi (es. python.exe non autorizzato) fino a intervento manuale | Cantiere 2 Regista, altri | ? | ? | ? |
| A02 | Guard once-per-day sull'alert approvazioni bloccate non funziona come previsto | Cantiere risposte email | ? | ? | aperto (noto) |
| A03 | Setup ripetuto a mano a ogni apertura di sessione Claude Code (contesto, file, permessi) | tutte le sessioni officina | ? | ? | ? |
| A04 | Correzioni manuali contate alla chiusura dei cantieri poster / IMAP / DM / leadgen — *da riprendere dai log di chiusura* | fabbrica | ? | ? | ? |
| A05 | Script estrazione/diagnostica debuggati per iterazioni multiple prima di girare | Cantiere 1 Regia sonora | ? | ? | chiuso? |
| A06 | Verifica manuale dello stato attuale di tool/modelli prima di ogni raccomandazione (rassegna quasi quotidiana delle novità) | progettazione cantieri | ~quotidiana | ? | aperto — è la versione manuale della Porta 2 |

**Candidati accoppiati (corsia riparazioni, 07/09):** A06 → 74 Find Skills;
Agent Reach (baseline). A03 → Claude-Mem (baseline) — condizionato al
SOSPESO 7.

---

## Ciclo di aggiornamento

Il registro si aggiorna in un solo punto: **alla chiusura di ogni cantiere**,
quando le correzioni manuali vengono già contate (PIANO_OPERATIVO §3).
Quella voce della checklist di chiusura diventa: *"conta le correzioni →
scrivi/aggiorna le righe del registro"*. Nessun altro momento di manutenzione:
se richiede un rito a parte, muore.

---

*Se questo registro contraddice quello che è successo davvero, ha ragione la realtà.*
