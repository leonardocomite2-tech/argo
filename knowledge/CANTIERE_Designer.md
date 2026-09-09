# CANTIERE — Designer: l'agente di web design

**5 settembre 2026 — v1**
Da leggere con `METODO_CANTIERI.md`, `NarraTours_Modello_Business.md` §1,
`CANTIERE_Skill_Tool.md` (le tre porte) e `PIANO_OPERATIVO_v3.md` §4 (voce "Pagine tour").

**Natura del documento:** un solco. Qui si decide la forma dell'agente, non l'estetica delle
pagine — quella nasce dal lavoro, dentro i vincoli che questo documento rende espliciti.

---

## 1. La gerarchia degli obiettivi, resa esplicita

"Bello ma se non capisci cosa hai davanti non ha senso" è già la gerarchia giusta; conviene
scriverla in una forma che un agente possa usare:

> **Chiarezza è un vincolo, non un obiettivo in competizione.** Prima si capisce cosa si ha
> davanti e cosa fare; poi, dentro quel vincolo, si stupisce quanto si vuole. Un design che
> sacrifica la chiarezza per l'effetto non è una scelta stilistica: è fuori specifica.

E i "risultati concreti" hanno un giudice che non è né tuo né dell'agente: **la misura sul
campo**. L'agente non deve avere ragione sul design — deve produrre varianti degne di essere
testate, e i numeri decidono. Questo scioglie in partenza le discussioni di gusto. Quale
strumento faccia da giudice dipende dal progetto e vive nella sua modalità (§3).

---

## 2. Il mestiere: cosa sa fare l'agente, ovunque lavori

Questo è il nucleo, e non cambia da progetto a progetto. Non è un elenco di regole di stile —
lo stile nasce dal lavoro — ma le competenze che l'agente porta con sé prima di sapere per chi
sta disegnando.

**Gerarchia e leggibilità.** Cosa si guarda per primo, cosa si legge, cosa si tocca. Un
visitatore deve capire dove si trova, cos'è in vendita e cosa fare, prima di ammirare
qualsiasi cosa. È il vincolo della §1 tradotto in pratica quotidiana.

**Conversione.** Dove va la chiamata all'azione, quanto testo regge una sezione, come si
riduce l'attrito di una decisione. L'agente non deve essere un esperto di marketing: deve
sapere che una pagina esiste per far succedere qualcosa, e che quel qualcosa vince sugli
effetti quando i due si scontrano.

**Budget di peso e prestazioni.** Ogni scelta visiva ha un costo in byte e in secondi.
L'agente ragiona a budget — un'animazione entra se se la merita, non perché è possibile. Su
qualunque piattaforma, il visitatore è quasi sempre su un telefono e spesso su una rete
mediocre.

**Mobile prima del desktop.** Non come slogan ma come ordine di lavoro: si disegna la
viewport stretta, poi si allarga. Il §4 lo rende verificabile.

**Distinguersi dal generico.** Il mestiere vero è far sembrare la pagina *non* un template.
Vale con un builder, con un framework o con HTML scritto a mano: cambiano gli strumenti, non
l'obiettivo.

**Un mestiere, non un'estetica.** Il nucleo non fissa uno stile: fissa il modo di lavorare che
rende difendibile qualsiasi stile. Le tecniche visive del momento evolvono in fretta, e per
questo vivono nell'indice delle skill (§5), non qui dentro.

## 3. La forma: nucleo + modalità

```
SKILL  designer (nucleo)          il mestiere della §2. Nessun progetto,
                                  nessuna piattaforma, nessun brand.

FILE   modalita/<progetto>.md     tutto ciò che è specifico:
                                  · brand e identità visiva
                                  · piattaforma di destinazione e cosa
                                    permette o impedisce
                                  · come si misura il risultato
                                  · componenti già approvati
```

Il nucleo non conosce nessun progetto; la modalità non contiene mestiere. Quando arriverà il
secondo progetto si scriverà la sua modalità e basta — **il meccanismo è generale dal primo
giorno, il contenuto no.** Ciò che si costruisce due volte è solo un file di testo: la regola
del due rispettata senza rinunciare alla riusabilità.

**La piattaforma sta qui, non nel nucleo.** È una proprietà del progetto, non dell'agente:
oggi NarraTours vive su GoHighLevel, domani un altro progetto vivrà su un framework, e il
mestiere della §2 non cambia di una riga. Quello che cambia è cosa si può fare e con quale
budget — e sono informazioni che l'agente riceve entrando in modalità.

### La modalità NarraTours

**Il brand non si inventa:** parte dall'identità già fissata nel documento di business —
sfondi neri caldi, crema, oro come unico accento, Playfair Display e DM Sans — e si arricchisce
coi componenti che emergono lavorando. Dove esiste un fatto, non serve una stima: vale anche
per il brand.

**Le condizioni di GoHighLevel**, da verificare quando la modalità verrà scritta davvero,
perché la piattaforma cambia in fretta:

- la base è lenta — le pagine GHL partono con punteggi mobile bassi e primi render sopra i
  4 secondi, quindi il budget di peso della §2 qui è più stretto che altrove;
- il margine di manovra sta nei code block: CSS custom per pagina e blocchi HTML/CSS/JS per
  ciò che il builder non fa;
- il template si riconosce ("ogni sito GHL sembra un sito GHL"), il che rende il punto
  *distinguersi dal generico* della §2 il lavoro principale, non un extra;
- il builder ha breakpoint separati, ed è lì che si verifica il mobile.

**Il giudice del risultato** è il test A/B nativo: fino a 5 varianti per step, vincitore a
significatività statistica, incluso in ogni piano. Sta nella modalità perché è lo strumento di
*questa* piattaforma; il principio — un giudice esterno decide, non il gusto — sta nella §1.

---

## 4. Il ciclo visivo: l'agente deve vedere ciò che produce

Un agente che scrive CSS e non guarda il risultato sta indovinando. Il nucleo include il
ciclo che è diventato pratica standard nel 2026:

```
produce → renderizza → si fa lo screenshot (viewport mobile per primo) →
guarda → corregge → ripete → solo alla fine lo mostra a te
```

In officina si fa con un browser pilotato dalla sessione (Playwright o equivalente). Le
iterazioni interne non ti costano attenzione: tu vedi la versione che l'agente stesso ha già
giudicato presentabile — con lo screenshot accanto, non con il codice.

Sotto il ciclo visivo, un **pavimento deterministico** che non si discute: contrasto
leggibile, resa corretta ai breakpoint, peso della pagina dentro il budget, niente errori
console. Sono controlli da script, non da giudizio — e girano prima che tu veda qualsiasi cosa.

---

## 5. Il collegamento con l'agente Skill/Tool

Hai ragione che le skill di design sono tante e in movimento continuo — ed è esattamente il
motivo per cui **il nucleo resta magro e non prova a contenerle**. La divisione:

- il **nucleo** contiene il mestiere che non cambia (gerarchia, chiarezza, budget, ciclo
  visivo) e i vincoli di piattaforma;
- le **tecniche che evolvono** (librerie di componenti, stili del momento, generatori di
  sezioni) vivono nell'indice dei candidati del cantiere Skill/Tool.

Le tre porte lavorano così per il Designer:

- **porta 1 (innesto):** quando il Designer si attiva su un lavoro, il suggeritore controlla
  l'indice e propone le skill di design pertinenti già catalogate;
- **porta 2 (radar):** "web design" diventa una **categoria permanente d'interesse** — il
  radar settimanale la incrocia anche senza un attrito aperto, perché qui la novità *è*
  il valore;
- **porta 3 (sportello):** le skill di design che trovi in giro entrano dall'intake, vengono
  ispezionate e categorizzate come tutte le altre.

Nota di dipendenza, non di blocco: questo collegamento funziona quando il cantiere Skill/Tool
avrà almeno il suo indice. Il Designer però **non aspetta**: parte con il nucleo e la modalità,
e si aggancia alle porte quando esistono.

---

## 6. Cosa produce, concretamente

Tre uscite, in ordine di frequenza attesa:

1. **Sezioni e pagine**, nel formato che la piattaforma della modalità richiede — su
   NarraTours oggi significa CSS custom e blocchi HTML/CSS/JS pronti da incollare, con lo
   screenshot di come devono apparire e le istruzioni di dove vanno.
2. **Varianti da testare** — quando il lavoro tocca una pagina che converte, l'uscita naturale
   sono due varianti argomentate, non una verità.
3. **Il template stabile dei tour** — che è la condizione di apertura del cantiere "Pagine
   tour" già nel tuo backlog: il Designer disegna il template, quel cantiere poi ci stampa
   dentro i contenuti in modo deterministico. Due cantieri che si passano il testimone.

**L'approvazione resta tua e resta visiva:** screenshot prima, codice dopo. Niente va online
senza il tuo sì — l'agente prepara, tu pubblichi. Quando una piattaforma permetterà la
pubblicazione via API e tu avrai deciso di alzare il livello, cambierà quel passaggio, non
il resto.

---

## 7. Le sette domande

```
CANTIERE: Designer

Cosa dimostra:    che un agente produce pagine che (a) superi il
                  pavimento deterministico, (b) approvi senza
                  redesign, (c) quando testate, battono l'esistente
Versione manuale: le pagine attuali del sito — esistono, convertono,
                  e sono il termine di paragone
Mattoni usati:    gate di approvazione; le tre porte Skill/Tool
                  (quando esistono); modalità = pattern dei file
                  identità già usato altrove
Pezzo nuovo:      nucleo della skill + il meccanismo delle modalità
                  + ciclo visivo con pavimento deterministico
                  (la modalità NarraTours è il primo contenuto,
                  non il pezzo nuovo)
LLM sì/no:        sì, ed è il suo mestiere — dentro il pavimento
                  deterministico e con giudice esterno (A/B)
Done when:        N pezzi reali pubblicati senza redesign, e almeno
                  un test concluso in cui la variante del Designer
                  batte l'esistente su una metrica del progetto
Costo se sbaglia: una variante che perde il test — cioè informazione
                  gratis. Nessun invio, nessuna spesa non approvata.
```

Il "done when" ha due stadi di natura diversa, ed è voluto: *pubblicato senza redesign* misura
la qualità del gusto e del processo; *vince un test* misura i risultati concreti. Il primo si
può raggiungere in settimane; il secondo dipende dal traffico, e va trattato come la chiusura
vera del cantiere, non come formalità.

---

## 8. Rischi

| Rischio | Mitigazione |
|---|---|
| Il "wow" appesantisce la pagina | Budget di peso nel pavimento deterministico, non nel giudizio. Più stretto dove la piattaforma parte lenta |
| Design bello su desktop, rotto sul telefono | Ciclo visivo mobile-first; breakpoint verificati da script |
| Deriva dal brand a forza di stupire | La modalità è il confine; l'oro resta l'unico accento finché il documento di business dice così |
| Dipendenza dal cantiere Skill/Tool non ancora chiuso | Il Designer parte da solo; le porte si agganciano dopo |
| Traffico troppo basso perché un test significhi qualcosa | Testare sulle pagine con più traffico, una variante per volta, e accettare che il secondo stadio richieda tempo |

---

## 9. Decisioni aperte

- Dove vive il ciclo visivo: Playwright in locale è l'ipotesi. Per ogni piattaforma va
  verificata la resa fedele fuori dal suo builder — su GHL il rendering a runtime potrebbe
  imporre screenshot sull'anteprima pubblicata invece che su file locali
- Se la modalità includa una libreria di sezioni approvate ("componenti benedetti") che
  crescono col lavoro — probabile sì, ma emerga dall'uso
- Come nominare e archiviare le varianti dei test, così che i risultati alimentino la
  modalità (le vittorie diventano componenti, le sconfitte note)
- Se e quando la pubblicazione diventi automatizzabile via API, per progetto — oggi si incolla

---

*Se questo documento contraddice quello che sta succedendo davvero, ha ragione la realtà.*
