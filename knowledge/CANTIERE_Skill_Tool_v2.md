# CANTIERE — Adozione di skill e tool

**7 settembre 2026 — v2** (sostituisce la v1 del 5/09)
Da leggere con `METODO_CANTIERI.md`, `PIANO_OPERATIVO_v3.md` §3 e `CONTESTO_PROGETTO_v0.4.md` §4.

**Natura del documento:** un solco. Dà la direzione e i criteri, non un elenco di prescrizioni.
Se un criterio impedisce la cosa giusta in un caso concreto, si deroga e si annota perché.

---

## 1. L'inversione che regge il cantiere — e i suoi due ancoraggi

Il problema non è valutare una lista di skill. È che **la lista è dalla parte sbagliata**.

> *"Questa skill è utile?"* non ha risposta. Ce l'hanno due domande diverse, entrambe
> verificabili:
> **"Risolve un attrito che ho davvero avuto, N volte?"** — e
> **"Avvicina una direzione che ho già dichiarato di volere?"**

Dove esiste un archivio di fatti reali, quell'archivio è il sistema. Qui gli archivi
sono **due**:

- **Il passato:** il registro degli attriti — correzioni manuali, escalation, passaggi
  ripetuti dei cantieri chiusi. Ancora la **corsia riparazioni**.
- **Il futuro già scritto:** il backlog con le condizioni di apertura (`PIANO` §4),
  il parcheggio con le condizioni di ripresa (`CONTESTO` §8), gli obiettivi del
  `Modello_Business`. Ancora la **corsia evoluzioni**.

Una proposta senza uno dei due ancoraggi è rumore, per quanto bella la risorsa.
Le chat che rispondevano "inutile" e i reel che rispondono "indispensabile" sbagliano
allo stesso modo: nessun aggancio.

---

## 2. Il registro degli attriti

Una riga per ogni cosa che è costata tempo o è stata corretta a mano, con: cosa
succedeva, in quale cantiere, quante volte, quanto costava, se è ancora aperta.

**Stato: popolato il 7/09** all'indietro sui cantieri chiusi (poster, lead-gen,
IMAP, risposte, DM) — 19 attriti con evidenza da DB/git/STATO.md, più i seed.
Vive in `knowledge/registro_attriti.md` nel repo, dove tutte le porte lo leggono.

**Un attrito senza un numero accanto vale poco.** "A volte è scomodo" non giustifica
l'installazione di niente; "otto volte in due cantieri, dieci minuti l'una" sì.

**Esito del primo accoppiamento (7/09):** su 25 attriti, ~5 hanno un candidato che
li tocca; su 41 candidati indicizzati, ~35 non toccano nessun attrito. Non è un
fallimento: è il filtro che funziona. La corsia riparazioni sarà spesso silenziosa —
la maggior parte degli attriti reali si risolve con codice interno, non con tool.

---

## 3. Il candidato, e cosa se ne fa

La lista diventa un **indice dei candidati** (`knowledge/indice_candidati.yaml`):
per ciascuno, cosa promette, da dove viene, il livello di fiducia della fonte
(ufficiale / community con storia / virale recente / da verificare).

L'indice non serve a decidere: serve ad avere qualcosa da confrontare **con i due
ancoraggi**. Il campo che decide è `attriti` (corsia riparazioni) più le note di
direzione (corsia evoluzioni). Il punteggio di promessa resta metadato di curatela.

Il valore della lista è la curatela, non lo stoccaggio. Le superfici di ricerca
esterne (find-skills, skills.sh, repo ufficiali) coprono la scoperta.

**Marketplace privato** (repo Git con `marketplace.json`): confermato come forma
di installazione pulita, **dopo** — quando esiste almeno una cosa promossa da
installare.

---

## 4. Un accoppiatore, due corsie, tre porte

Un solo componente di giudizio — **l'accoppiatore** — con due domande:

**Corsia riparazioni** *(veloce, frequente, economica)*
> Questa risorsa risolve un attrito con un numero?
Alimenta il suggerimento all'apertura (Porta 1) e l'alert del radar (Porta 2).
Modello piccolo, contesto ridotto (registro + indice).

**Corsia evoluzioni** *(rara, costosa, intelligente)*
> Questa risorsa avvicina una condizione già dichiarata nel backlog/parcheggio/
> obiettivi — o abilita qualcosa che nessun cantiere ha ancora nominato?
Gira col **modello migliore disponibile e il contesto pieno**: CONTESTO, PIANO,
Modello Business, registro, indice, STATO. È l'unico punto del sistema dove pagare
il ragionamento completo ha senso — ed è raro, quindi costa poco.
Due trigger, mai di più:
- **alla chiusura di un cantiere** ("hai appena chiuso X: con Y a catalogo, il
  cantiere Z del backlog è diventato più piccolo/più vicino");
- **un giro mensile** sul catalogo intero.
Le evoluzioni non scadono: una cadenza più alta produce solo rumore.
**Propone soltanto.** Mai apre cantieri, mai installa. La regola del cantiere
unico resta di Leonardo.

Le tre porte restano tre momenti dello stesso agente, che leggono e scrivono gli
stessi artefatti (registro + indice):

**Porta 1 — l'innesto (officina).** All'apertura di un *progetto nuovo*, dentro le
sette domande. Consulta solo ciò che è già in casa. Due righe o silenzio. Sui
cantieri passati avrebbe detto quasi niente — il suo valore è sui cantieri futuri
di tipo nuovo (frontend, marketing), dove l'indice è pieno di risorse oggi senza
attrito.

**Porta 2 — il radar (fabbrica).** Job settimanale sul VPS: fonti esterne
incrociate con gli attriti aperti (corsia riparazioni). Telegram solo a
corrispondenza. Il silenzio per un mese è comportamento corretto.
La corsia evoluzioni NON gira nel radar settimanale: ha i suoi due trigger.

**Porta 3 — lo sportello (officina, su chiamata).** Gli porti una skill — link o
nome — e lui la ispeziona in sandbox, la categorizza, risponde alle domande sul
catalogo. Sostituisce l'aggiornamento quotidiano manuale della lista.

Il ciclo si chiude alla chiusura di ogni cantiere: lì si contano le correzioni
(→ registro), e lì scatta il primo trigger della corsia evoluzioni.

Il catalogo vive nel repo (`knowledge/`), dove tutte le porte lo leggono.
L'innesto della Porta 1 converge con l'Officina: l'Officina è il contenitore,
questo è il contenuto.

---

## 5. Valutare senza rischiare

**Valutazione e installazione sono due posti diversi, e non si sovrappongono mai.**

- La valutazione gira in un **ambiente usa-e-getta** — mai il VPS di produzione,
  mai la sessione in cui lavori.
- L'installazione sul sistema reale resta **una decisione tua**, su proposta scritta.
- Skill di sola lettura si provano; quelle che scrivono, eseguono o installano hook
  passano da una lettura del codice prima di qualsiasi prova.
- Un hook attivo costa a **ogni sessione futura**. È il costo che si dimentica.

L'asimmetria: **un tool sbagliato costa per sempre, un tool mancato costa poco.**
Nel dubbio si aspetta — l'attrito resta nel registro, il candidato pure, e la
condizione di backlog non scade.

---

## 6. La forma del cantiere

```
CANTIERE 1 — REGISTRO E INDICE                    (manuale — QUASI CHIUSO)
   ✔ registro popolato all'indietro (7/09, 19 attriti con evidenza)
   ✔ indice normalizzato (41 voci; baseline 65 da importare)
   ✔ primo accoppiamento manuale corsia riparazioni (7/09)
   ○ import baseline 65 + primo giro corsia evoluzioni sul catalogo pieno

CANTIERE 2 — INNESTO + SPORTELLO                  (officina)
   porta 1: suggerimento all'apertura di progetti nuovi ·
   porta 3: intake conversazionale, ispezione in sandbox, categorizzazione ·
   accoppiatore a due corsie (il giro evoluzioni manuale del cantiere 1
   è la sua versione manuale)

CANTIERE 3 — RADAR                                (fabbrica)
   porta 2: job settimanale VPS (corsia riparazioni) ·
   trigger evoluzioni: a chiusura cantiere + mensile ·
   Telegram solo a corrispondenza
```

**Come misurare il cantiere 2.** Tre metriche, le ultime due sono quelle che contano:
- *All'indietro:* sui cantieri chiusi, il suggeritore propone ciò che avrebbe
  aiutato davvero?
- *In avanti, riparazioni:* **adottato e tenuto** a 30 giorni, non "suggerito".
- *In avanti, evoluzioni:* **proposte diventate cantieri** (o esplicitamente
  parcheggiate con condizione), non proposte fatte. Un consigliere che propone
  dieci cose al mese è rotto quanto un radar che avvisa ogni settimana.

---

## 7. Struttura degli agenti

```
skill  registro-attriti     come si scrive e si aggiorna un attrito
skill  valuta-candidato     come si legge una skill prima di provarla

subagent  accoppiatore      DUE CORSIE:
                            · riparazioni — attrito ↔ candidato
                              (porte 1 e 2; modello piccolo, contesto ridotto)
                            · evoluzioni — candidato ↔ direzione dichiarata
                              (trigger chiusura-cantiere e mensile;
                               modello grande, contesto pieno)
subagent  ispettore         legge il codice di un candidato in sandbox e
                            riferisce cosa fa — non se è buono (porta 3)

worker    radar             porta 2: job settimanale sul VPS — fonti,
                            incrocio con attriti aperti, riga in events,
                            Telegram solo a corrispondenza

hook   blocca l'installazione di qualsiasi cosa fuori dalla sandbox
       senza approvazione esplicita
```

**L'ispettore descrive, non giudica.** **Nessun agente installa niente.**
**La corsia evoluzioni propone, non decide** — l'output è sempre una proposta
scritta con l'ancoraggio esplicito (quale condizione di backlog/parcheggio/
obiettivo avvicina, e di quanto).

**Dove gira:** valutazione e corsia evoluzioni in officina. Il radar in fabbrica.

---

## 8. Le sette domande (aggiornate)

### Cantiere 1 — Registro e indice — quasi chiuso
```
Done when:        ✔ registro popolato · ✔ accoppiamento riparazioni fatto ·
                  ○ baseline 65 importata · ○ un giro evoluzioni manuale
                  sul catalogo pieno (è la versione manuale della corsia)
Esito parziale:   5 match su 25 attriti, ~35 candidati su 41 senza attrito.
                  Il filtro funziona; le porte si ridimensionano di conseguenza.
```

### Cantiere 2 — Innesto + Sportello
```
Cosa dimostra:    che all'apertura di un progetto nuovo esce il suggerimento
                  giusto (o il silenzio giusto), che una skill nuova entra nel
                  catalogo conversando, e che la corsia evoluzioni produce
                  proposte ancorate invece di rumore
Versione manuale: il cantiere 1, fatto a mano (incluso il giro evoluzioni)
Mattoni usati:    registro e indice, skill nuovo-cantiere (Officina)
Pezzo nuovo:      trigger "progetto nuovo" + intake con sandbox + prompt
                  della corsia evoluzioni
LLM sì/no:        sì: accoppiamento semantico (2 corsie), ispezione, categorie
Done when:        test all'indietro + ritenzione a 30gg (riparazioni) +
                  proposte-diventate-cantieri (evoluzioni)
Costo se sbaglia: contenuto da sandbox e approvazione manuale
```

### Cantiere 3 — Radar
```
Cosa dimostra:    che il sistema si accorge da solo di una novità rilevante
                  per un attrito aperto, senza rumore — e che i due trigger
                  della corsia evoluzioni scattano nei momenti giusti
Versione manuale: la rassegna quasi quotidiana (attrito A06, ~quotidiano —
                  il numero più alto del registro: è la giustificazione
                  principale di questo cantiere)
Mattoni usati:    worker, dedup_key, Telegram, digest, accoppiatore
Pezzo nuovo:      connettori alle fonti + soglia di rilevanza
LLM sì/no:        sì, per l'incrocio novità ↔ attriti
Done when:        4 settimane in produzione; ogni avviso pertinente
                  (il numero di avvisi NON è la metrica)
Costo se sbaglia: un messaggio Telegram di troppo. Nessuna installazione.
Si apre quando:   il registro esiste (✔) e la porta 1 funziona
```

---

## 9. Rischi

| Rischio | Mitigazione |
|---|---|
| Codice arbitrario da fonti non fidate | Sandbox usa-e-getta, mai il VPS. Ispezione prima della prova. |
| Accumulo: skill installate degradano ogni sessione | Metrica di ritenzione; disinstallare è un esito normale |
| Il registro non viene aggiornato e muore | Si aggiorna alla chiusura dei cantieri, dove già conti le correzioni |
| Il suggeritore diventa rumore | Riparazioni: solo attriti con numero. |
| **La corsia evoluzioni diventa un venditore di novità** | Ancoraggio obbligatorio a backlog/parcheggio/obiettivi; due soli trigger; metrica = proposte diventate cantieri |
| Costruire tutto questo per cinque attriti veri | Il cantiere 1 l'ha misurato: 5 match. Le porte si sono ridimensionate PRIMA di essere costruite — la ragione per cui il cantiere 1 viene primo ha funzionato |

---

## 10. Decisioni

**Chiuse (7/09):**
- Registro e indice vivono come **file nel repo** (`knowledge/`) — finché non fa male.
- Marketplace privato: **dopo il cantiere 1**, quando c'è qualcosa da installare.
- La parte evoluzioni: **seconda corsia dell'accoppiatore**, non quarta porta.
  Modello grande, contesto pieno, due trigger, metrica proposte→cantieri.
- `nuovo-cantiere` e Porta 1: **una skill sola** (regola del due: si separa se
  un secondo trigger reale lo richiede).

**Aperte:**
- Quanto spingere la scoperta automatica di candidati nuovi (rischio: ricostruire
  un aggregatore che esiste già — find-skills/skills.sh coprono la scoperta).
- Frequenza reale del radar: settimanale è l'ipotesi, i primi avvisi diranno.
- Sorte dei SOSPESI residui del registro (6,7,8,9,10,11,12) — non bloccano le porte.

---

## Changelog

| Data | Cosa | Perché |
|---|---|---|
| 5/09 | v1 | Prima stesura: inversione, registro, tre porte, sandbox |
| 7/09 | v2 — aggiunta la **corsia evoluzioni** come seconda corsia dell'accoppiatore (ancorata a backlog/parcheggio/obiettivi, modello grande, due trigger, metrica proposte→cantieri); registro popolato e primo accoppiamento fatto; chiuse 4 decisioni aperte; rischi ed esiti aggiornati coi numeri reali | Il sistema v1 sapeva solo riparare: mancava la parte che usa il catalogo per proporre evoluzioni. Aggiunta senza tradire l'inversione: anche le evoluzioni hanno un archivio di ancoraggio — il futuro già dichiarato nei documenti |

---

*Se questo documento contraddice quello che sta succedendo davvero, ha ragione la realtà.*
