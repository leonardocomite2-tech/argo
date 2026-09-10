# Modalità — NarraTours

Bozza compilata il 09/09/2026, cantiere Designer passo 1. Completata il 09/09/2026 con
l'esito della ricognizione manuale nel builder GoHighLevel. Solo dati misurati sul sito
reale (vedi `baseline_narratours.md`), osservati a mano nel builder, o decisi nei documenti
di progetto. Dove manca un dato: `[DA COMPILARE]`/`[DA VERIFICARE]` con la domanda precisa —
non stimato.

## 1. Brand

**Colori dichiarati** (fonte: `NarraTours_Modello_Business.md` — riferimento canonico, non
si tocca): `#0f0a06` `#1a1410` `#faf9f6` `#c49a3c` `#e8c46a` `#6ee7a0`.

Confermati esatti sul sito servito: `#0f0a06` (sfondo scuro), `#faf9f6` (chiaro, testo/CTA),
`#c49a3c` (oro, sfondo CTA). Non osservati nei punti campionati: `#e8c46a`, `#6ee7a0` — non
smentiti, solo non intercettati dal campionamento (dettagli in `baseline_narratours.md`).

**Divergenza testo — chiusa (09/09/2026)**: il riferimento resta `#1a1410`
(`NarraTours_Modello_Business.md`, non si modifica); il sito serve oggi `#1a1714` sul testo
di body/h1/h2 delle pagine tour. Non è un errore da correggere ora: si allineerà quando il
Designer toccherà quelle parti. Annotata, non urgente.

**Font dichiarati**: Playfair Display + DM Sans — restano il brand di riferimento.
**Confermato**: sono i font effettivamente resi su schermo (computed style, misurato in
baseline), su tutte e 6 le pagine. Presente anche Font Awesome 5 per le icone. La pagina
`yourservice-it` carica in più la famiglia Inter.

**Conflitto Typography/CSS globale — debito tecnico (non urgente, non risolto qui)**: la
ricognizione manuale nel builder (09/09/2026) ha trovato che *Typography* imposta **Inter**
per Headline e Content, e il CSS globale (Websites > NarraTours > Settings > Tracking &
scripts > Body tracking code) forza Inter con `!important` su `body *`. Eppure il computed
style misurato in baseline mostra Playfair Display/DM Sans vincenti sulle 4 pagine tour
(Inter compare solo su `yourservice-it`, coerente col fatto che è l'unica pagina dove la
baseline aveva rilevato quella famiglia). Le due osservazioni sono in apparente
contraddizione: non risolta in questo passo, da bonificare in un intervento dedicato
futuro — non "di passaggio". **Il brand di riferimento resta Playfair Display + DM Sans;
Inter non appartiene al brand.**

**Spiegazione candidata (non verificata)**: `body *` ha specificità minima (tipo +
universale); a parità di `!important` vince la regola più specifica, e i CSS dei blocchi
del builder usano quasi certamente selettori di classe — che battono `body *` legittimamente,
senza bisogno di un altro `!important`. Se questo è corretto, non c'è nessun mistero: è
cascata CSS normale. **Da confermare alla prima bonifica guardando un selettore reale
(devtools sulla pagina pubblicata); fino ad allora non indagare oltre — non è né urgente né
bloccante.**
[DA VERIFICARE: la specificità-per-classe spiega davvero il caso, o il Body tracking code
non viene iniettato ovunque?]

**Tono**: CLAUDE.md fissa il tono per email/SMS/messaggi in uscita verso host e prospect:
lei cordiale, mai formalismi da ufficio (deciso 18/08). **Questo governa la comunicazione
outbound (email, SMS), non necessariamente il copy del sito stesso**, che oggi è in inglese,
registro marketing turistico informale ("You only have a few days in Rome", "Don't waste
time figuring out what to do"). Sono due canali e due pubblici diversi (turista che legge il
sito vs host/prospect che riceve un'email).
[DA COMPILARE: il copy del sito NarraTours per il turista deve seguire un tono a parte
(quale?), o si applica comunque "lei cordiale" tradotto in inglese/altre lingue? Il sito è
solo in inglese o multilingua? Chi decide il copy delle pagine tour — è nel perimetro del
Designer o resta editoriale/marketing?]

## 2. Piattaforma

GoHighLevel. Ricognizione manuale nel builder (09/09/2026).

**Dove va il codice**
- **CSS per pagina**: Builder > icona pennello "Custom CSS" > modale con editor. Oggi vuoto
  su tutte le pagine.
- **CSS globale**: non esiste un campo dedicato; vive in Websites > NarraTours > Settings >
  Tracking & scripts, campi "Head tracking code" e "Body tracking code" (accettano
  `<style>`; il Body ne contiene già uno con `!important` — vedi conflitto font in §1).
- **Blocchi di codice**: un solo elemento "Code" (categoria Custom), editor "Custom
  Javascript/HTML". Nessun limite dichiarato. **Non viene eseguito nel canvas del
  builder**: serve "Preview Custom Codes" o la pagina di anteprima.
- **Header/Footer Tracking — GLOBALI, non per pagina (confermato da Leonardo, 10/09/2026).**
  L'ingresso nel builder è `</>` "Tracking Code" > tab "Header Tracking" / "Footer Tracking",
  un'icona che compare per-pagina — ma il contenuto che ci vive è **condiviso a livello sito**:
  stesso Header e stesso Footer su tutte e 6 le pagine misurate (evidenza indipendente già
  in baseline: `document.title` risultava "NarraTours — Header" su tutte e 6, non solo su
  `yourservice-it` — comportamento che un blocco per-pagina non spiegherebbe). Confermato
  anche nel commento di testa di `pagine/yourservice-it/blocco_header.html` e
  `blocco_footer.html`. **Conseguenza pratica**: un blocco globale non va mai incollato su
  una singola pagina di prova — modificarlo tocca tutte le pagine live. Vedi regola 6 sotto.

**Breakpoint**: il builder distingue Desktop / Tablet / Mobile ma non dichiara le larghezze
in px — non essendo dichiarate dalla piattaforma, restano validi quelli misurati nel CSS
effettivamente servito (`baseline_narratours.md`): 380, 480, 640, 760, 767/768, 860/861,
900, 979/980, 991, 1024, 1100, 1200 px (con piccole variazioni tra tipi di pagina).

**Font**: caricamento di font custom possibile ("Upload Fonts" nel selettore). Per il
conflitto Typography/CSS globale vs font effettivamente resi, vedi §1.

**Anteprima senza login**: `https://sites.leadconnectorhq.com/preview/<pageId>` (esempio
Blood & Glory: `/preview/2j4hch7LuGGFazt6b7yD`). Mostra la versione **salvata**, non quella
pubblicata — Save e Publish sono azioni separate e l'autosave è disattivato.

**"Optimize JavaScript" è ON a livello sito**: i custom code vengono caricati in lazy-load.
Conseguenza per ogni script che scriveremo: non assumere esecuzione immediata al load; la
verifica vera si fa sempre sull'URL di anteprima, mai solo sul render locale.

**Cronologia versioni: assente** — solo undo di sessione. Vedi regola 1 sotto.

### Regole di lavoro (derivate dai fatti sopra)

1. **Backup prima di tutto.** Prima di qualsiasi intervento su una pagina, il contenuto di
   ogni suo blocco Code va copiato in file nel repo (`pagine/<slug>/blocco_NN.html`), commit
   locale. GHL non ha rollback: **il repo è la cronologia versioni**. Da quel momento la
   sorgente è il repo: si modifica lì, si verifica col ciclo visivo, si incolla in GHL.
2. **Specificità.** Ogni CSS di pagina deve battere il globale che usa `!important` su
   `html`, `body`, `body *`. Regola pratica: scoping con un id o data-attribute di pagina sul
   wrapper e selettori più specifici del globale; `!important` solo come ultima risorsa,
   annotandolo.
3. **Il render locale** avviene dentro la shell reale: HTML del blocco + CSS globale del
   sito (già scaricato in baseline) + font reali. Questo misura il blocco isolato, **non**
   equivale al peso dell'intera pagina — la verifica finale sul budget (§3) va sempre fatta
   sull'URL `/preview/`, non sulla ricostruzione locale (vedi nota di conflitto in fondo).
4. **Pagine di prova**: si creano come pagine nuove non linkate, con
   `<meta name="robots" content="noindex">` **[CONTRADDETTO, 10/09/2026 — non seguire alla
   lettera finché non verificato]** — questa regola diceva di inserirlo "a mano nel Header
   Tracking della pagina", ma la scoperta di oggi (sopra) è che l'Header Tracking è
   **condiviso a livello sito**: se è davvero lo stesso campo su tutte le pagine, un
   `noindex` messo lì deindicizzerebbe l'intero sito, non solo la pagina di prova. Non
   risolto qui — è una decisione di Leonardo su come creare la pagina di prova in Fase C
   (esiste un campo SEO/robots per-pagina separato nel builder? Da verificare prima di usare
   questa regola, non da assumere).
5. **Niente modifiche al sito live in questo cantiere**: ogni lavoro avviene su pagina di
   prova o su bozza salvata e mai pubblicata. Pubblicare è sempre e solo un'azione manuale
   di Leonardo, fuori dal cantiere.
6. **Locale o globale, dichiaralo prima di ogni consegna.** Per ogni blocco toccato,
   dichiarare esplicitamente se è locale alla pagina (entra nella pagina di prova) o globale
   /condiviso a livello sito (mai in una pagina di prova — una modifica lì tocca tutte le
   pagine live, serve una decisione esplicita a parte). Non dedurlo dal nome del file o
   dall'aspetto: verificarlo (commento nel blocco, conferma diretta, o evidenza indipendente
   come nel caso Header/Footer sopra). Regola nata da un errore quasi fatto (10/09/2026): le
   istruzioni d'incolla di una consegna includevano il footer, poi scoperto globale.

## 3. Budget

La baseline (`baseline_narratours.md`, misurata il 09/09/2026: 8-8.5MB le pagine tour, 6MB e
330 richieste `yourservice-it`, pavimento FAIL su tutte e 6 le pagine) è il **termine da
battere, non il tetto da rispettare** — sono i numeri di oggi, e oggi falliscono anche loro.

**Regola operativa**: ogni intervento riduce o al più lascia invariato il peso della pagina
che tocca, mai lo aumenta.

**Soglie assolute per pezzi nuovi**: non ancora fissate — emergeranno dai primi lavori
reali, marcate come provvisorie quando arriveranno.

Numeri di riferimento (oggi, per tipo di pagina):
- **Pagina tour singola**: ~8.6 MB totali, ~100 richieste, ~6 MB in immagini.
- **Pagina bundle**: ~2.8 MB totali, ~83 richieste.
- **Pagina servizio/host** (`yourservice-it`): ~6.1 MB totali, 330 richieste (molto più
  alto delle altre, verosimilmente script terzi/tracking: non replicare quel numero, è già
  un problema lì).
- **Font**: 135 KB (pagine tour/bundle) — 285 KB (`yourservice-it`, carica anche Inter).
- **Primo render**: tra 508 e 1972 ms sulle pagine osservate — nessuna soglia dura ancora
  fissata, solo il range reale osservato.

## 4. Ciclo visivo

Ambiente: VPS di produzione (Hostinger KVM1, 3.8 GiB RAM, ora con **swap 2GB** aggiunto per
il cantiere Designer — vedi report di fattibilità). Chromium headless via Playwright,
installato dentro `.claude/skills/designer/` (progetto npm autocontenuto, non in
`tools/visual/`).

**RAM reale misurata durante la prova di fumo** (una pagina tour, viewport mobile, VPS in
produzione con i 4 container attivi): RSS massimo processi Chromium **~1063 MiB**, RAM
"available" host mai scesa sotto **~1844 MiB**, swap usato **~1 MiB** (praticamente
inutilizzato).

**Regola di migrazione (concordata)**: tre esecuzioni consecutive con RSS Chromium > 1,2 GB
o RAM available < 500 MB → il ciclo trasloca sul PC Windows (`D:\NarraTours`) senza
ridiscuterne (vedi § Fallback nel brief originale).

**Versione Playwright bloccata dal lockfile** (`package-lock.json` dentro
`.claude/skills/designer/`): aggiornamenti solo deliberati, mai automatici.

**Log**: ogni run dovrà scrivere una riga (data, pagina, RSS Chromium, peso pagina, esito
pavimento) in un CSV dentro `output/` (`output/log_run.csv`, gitignored come il resto di
`output/`). **Non ancora implementato negli script** consegnati in questo passo
(`cattura.mjs`/`pavimento.mjs`) — regola registrata qui, implementazione da fare al prossimo
tocco degli script.

**Node non è nei pacchetti di sistema**: installato via nvm (`~/.nvm`, versione fissata in
`.claude/skills/designer/.nvmrc` = `24.18.1`). nvm non esiste per processi non interattivi
(cron, systemd, sessioni diverse da quella in cui è stato installato): **non lanciare mai
solo `node script.mjs`** in un contesto non interattivo — usare il binario assoluto
(`~/.nvm/versions/node/v24.18.1/bin/node`) o caricare esplicitamente `~/.nvm/nvm.sh` in
testa allo script di lancio.

**Niente Lighthouse**: non installato (rimosso dal piano su richiesta di Leonardo). Regola
valida per ogni script di questa modalità: **un solo Chromium alla volta**, mai due browser
insieme, chiuso sempre in `finally`. `pavimento.mjs` misura peso/richieste/primo-render
direttamente con gli eventi di rete di Playwright, non con un audit Lighthouse.

**Comandi**:
```bash
cd /root/argo/.claude/skills/designer
export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

node scripts/cattura.mjs <url-o-file-html> [--domains=...] [--out=output]
node scripts/pavimento.mjs <url-o-file-html> [--domains=...] [--budget-kb=NNN] [--out=output]
```
Navigazione consentita per default a `narra-tours.com` **e** `sites.leadconnectorhq.com`
(l'anteprima GHL, regola 3 in §2, è flusso standard di verifica — non deve dipendere da un
flag da ricordare). `--domains` resta disponibile per estendere l'elenco a casi eccezionali.
Output (screenshot, snapshot di accessibilità, report JSON, log CSV) in `output/` (ignorata
da git).

**Log CSV** (`output/log_runs.csv`, implementato in `cattura.mjs` e `pavimento.mjs`): una
riga per run — timestamp ISO, script, URL/file, RSS massimo Chromium (MiB), RAM available
minima (MiB), peso pagina in KB (`n.d.` per `cattura.mjs`, che non misura il peso), esito
pavimento (`PASS`/`FAIL`/`n.a.` per `cattura.mjs`), durata (s). Verificato con una run reale
il 09/09/2026: `1175` MiB RSS massimo, `1675` MiB RAM available minima, `8687` KB, `FAIL`,
`70.0` s — sotto la soglia di migrazione (1,2 GB / 500 MB) ma con margine più stretto della
prima misura (`baseline_narratours.md` aveva registrato 1063 MiB/1844 MiB su una run più
leggera, solo screenshot senza axe-core+5 breakpoint).

**Discovery skill Claude Code**: verificato che `node_modules/` dentro
`.claude/skills/designer/` (22 MB, 214 file) non ha causato warning né rallentamenti
visibili nella sessione in cui è stato installato — la skill `designer` è comparsa
normalmente nell'elenco. Da tenere d'occhio se in futuro il progetto npm crescesse molto.

## 5. Misura

Split test nativo **non disponibile sui Websites**, solo sui **Funnels** (CONTROL/VARIATION,
metriche: Page Views, Opt-Ins, Sales, Earnings/Page View). Conseguenza: il secondo stadio
del "done when" del cantiere (vincere un test) richiederà di duplicare la pagina bersaglio
in un Funnel — decisione rimandata a quando ci si arriverà. Per il primo stadio (pubblicato
senza redesign) bastano i numeri del pavimento e il confronto con la baseline.

## 6. Componenti

(vuota — si riempie con i componenti approvati da Leonardo)

## 7. Riferimenti

`riferimenti.md` creato vuoto accanto a questo file, alimentato dalla ricognizione (§3 di
SKILL.md) quando il Designer farà il primo lavoro sopra soglia.

## 8. Bonifica yourservice-it — Fase B (10/09/2026)

Debiti e limiti trovati bonificando `pagine/yourservice-it/` (cantiere Designer, passo 2).
Test di fedeltà N.1 confermato prima di intervenire (h1:2, crash React, 404-equivalente
tutti riprodotti in locale — vedi `pagine/yourservice-it/_ricomposizione/`).

**Debito di brand — oro come testo su sfondo chiaro, NON risolto qui.** `#c49a3c` usato come
colore di *testo* su crema/bianco (em nell'h1 di entrambe le hero, eyebrow label in
blocco_01/02/03) è a **2,48–2,61:1** — sotto anche la soglia "testo grande" (3:1). Lo stesso
oro su sfondo scuro è a **7,53:1** (ottimo). Non corretto in questa bonifica: è un colore di
brand (`NarraTours_Modello_Business.md`, §1 sopra) usato su tutto il sito, non solo su questa
pagina — cambiarlo qui soltanto creerebbe incoerenza tra pagine. Opzioni per quando si deciderà
(nessuna scelta operata):
  (a) testo scuro dichiarato (`#1a1410`/reale `#1a1714`) al posto dell'oro quando il testo è
      su sfondo chiaro — l'oro resta riservato a sfondi scuri/usi non testuali;
  (b) un oro più scuro riservato al testo-su-chiaro — **`#8c6e2a`** è il primo valore della
      stessa tinta/saturazione che raggiunge **4,57:1** su crema (calcolato, candidato non
      approvato);
  (c) rivedere dove il brand usa sfondi chiari, che nella palette dichiarata sono l'eccezione
      rispetto allo sfondo scuro dominante.

**Contrasto footer — corretto nel repo, NON incollato: è un blocco globale
(10/09/2026).** `blocco_footer.html` è l'Header/Footer Tracking, condiviso a livello sito
(vedi §2 sopra) — modificarlo tocca tutte le pagine live, non solo `yourservice-it`. Il fix
di contrasto (alpha 0,25/0,35/0,42 → 0,5 su `.nt-footer-copy`/`.nt-footer-legal a`/
`.nt-footer-tagline`/`.nt-footer-col-title`, stesso colore dichiarato, nessuna implicazione
di brand) **resta committato nel repo** ma non entra nella pagina di prova di Fase C — è una
modifica globale, richiede una decisione esplicita di Leonardo su quando pubblicarla (tocca
il footer di tutte e 6 le pagine insieme). Rapporti di contrasto già calcolati e verificati
(§ sopra nel commit `93eb9ec`): 2,10:1→5,12:1 (copy/legal), 3,91:1→5,12:1 (tagline),
3,05:1→5,12:1 (col-title) — tutti sotto la soglia AA 4,5:1 prima del fix.

**H1 doppio — risolto correggendo il criterio del pavimento, non la pagina (10/09/2026).**
`.nt-p1-hero` (desktop) e `#ntHero` (mobile v3) coesistevano sempre nel DOM; ho aggiunto
`display:none` reciproco a 861px (soglia scelta perché già usata in `blocco_01.html` per il
proprio collasso di layout — **non è la soglia dichiarata dal builder GHL, che non la
dichiara** — verificata con un test dedicato di larghezze 820-900px, nessuna finestra
morta/doppia: PASS). A quel punto `pavimento.mjs` continuava a misurare "h1: 2": contava i
nodi grezzi del DOM, non l'albero di accessibilità. **Decisione di Leonardo: il criterio era
sbagliato, non la pagina** — due h1 nel sorgente HTML sono validi in HTML5 finché uno solo è
esposto per viewport; un h1 dietro `display:none` esce dall'albero di accessibilità, uno
screen reader ne vede uno solo. Uno script che rimuovesse attivamente il nodo dal DOM sarebbe
stato più fragile (su GHL "Optimize JavaScript" è ON, i custom code sono lazy-loaded — uno
script così girerebbe tardi, flash quasi garantito) per un problema che non esiste davvero.
**Vedi §9 sotto** per la correzione allo strumento e il risultato: ora `pavimento.mjs` misura
1 h1 esposto su `yourservice-it` bonificato — **chiuso**.

Resta aperta, come debito separato, la causa strutturale che ha prodotto il doppio h1: vedi
"Duplicazione desktop/mobile del markup" sotto — lì anche i numeri Vimeo/form corretti.

**Duplicazione desktop/mobile del markup — debito unico (10/09/2026).** Tre sintomi diversi,
stessa causa: il markup desktop e quello mobile di `yourservice-it` sono duplicati e mai
rimossi dal DOM, solo nascosti per viewport (nessun blocco usava `display:none` prima di
questa bonifica). Sintomi misurati:
  - **H1 doppio** (sopra) — chiuso lato criterio pavimento, ma la duplicazione fisica del
    markup resta (due `<h1>` nel sorgente, uno sempre `display:none`).
  - **6 iframe Vimeo su 3 video distinti** (non 7, correzione ai numeri dell'orientamento del
    cantiere), ciascuno duplicato desktop+mobile — mai rimosso dal DOM, quindi scaricato due
    volte anche se un lato è collassato.
  - **2 iframe form GHL con lo stesso `id`** (`inline-bfJq2874KQlSBFYmxq87`) duplicato tra
    `blocco_03.html` (desktop) e `blocco_body_mobile_per_host.html` (mobile) — id duplicato
    nel DOM quando entrambi coesistono; non isolato con certezza come causa di un errore
    console specifico (rumore Cloudflare Turnstile nell'ambiente di test, vedi sotto).
Il rimedio è lo stesso per tutti e tre: unificare in un markup responsive unico invece di due
sezioni parallele nascoste per viewport. **Candidato principale del prossimo intervento**, non
di questa Fase B (che si è fermata al criterio del pavimento per l'h1, senza toccare la
struttura).

**Limite di piattaforma — Cloudflare Turnstile blocca l'evento `load` di Playwright.** La
pagina reale (e la ricomposizione locale) caricano un widget GTranslate (`cdn.gtranslate.net`)
e/o un form GHL (`api.leadconnectorhq.com`) protetti da una sfida Cloudflare Turnstile
(`challenges.cloudflare.com`, `hagen.challenges.cloudflare.com`). In questo ambiente (sandbox
di sviluppo, non il VPS di produzione) quella sfida crea richieste `blob:` pendenti che
bloccano indefinitamente `waitUntil:'load'` — confermato sia sulla pagina live
(`https://narra-tours.com/yourservice-it`) sia sulla ricomposizione locale. **Non è un problema
dei blocchi**: è un'interazione tra l'automazione headless e il bot-management di Cloudflare,
probabilmente dipendente dall'IP di uscita dell'ambiente da cui gira `pavimento.mjs`/
`cattura.mjs` (il VPS di produzione potrebbe non essere flaggato allo stesso modo). Per questa
bonifica ho escluso `blocco_gtranslate.html` dalla ricomposizione locale (la sua posizione nel
builder era comunque già "DA CONFERMARE", vedi commento nel file) — sufficiente a far
completare `load`. **Se ricapita eseguendo il ciclo visivo dal VPS reale con GTranslate/form
incluso, non è un bug della pagina: verificare prima se è lo stesso meccanismo (richieste
pendenti verso `challenges.cloudflare.com`) prima di sospettare i blocchi.** Anche un residuo
"Cannot read properties of undefined (reading 'querySelector')" osservato una volta nel
pavimento (1 errore pagina su una run) è verosimilmente riconducibile a questa stessa
interazione Turnstile/axe-core, non a codice nei blocchi (tutte le chiamate `querySelector`
nei blocchi sono verificate con guardia `if (...)` prima dell'uso).

## 9. Correzione a `pavimento.mjs` — criterio h1 (10/09/2026)

Lo script (`.claude/skills/designer/scripts/pavimento.mjs`) contava gli `<h1>` con
`document.querySelectorAll('h1')`: un conteggio dei nodi grezzi del DOM, senza filtrare per
visibilità. Il caso yourservice-it (§8 sopra) ha dimostrato che è il criterio sbagliato: due
`<h1>` nel sorgente sono markup HTML5 valido finché uno solo è esposto all'utente/screen
reader per volta (caso reale: varianti desktop/mobile con lo stesso ruolo semantico, mai
entrambe visibili insieme) — non è un problema di accessibilità né di SEO. Contare i nodi
grezzi misurava una cosa diversa da quella che il pavimento vuole verificare.

**Cosa misurava prima**: `h1Count` = numero di `<h1>` presenti nel DOM, qualunque fosse il
loro stato di visibilità. Un `<h1>` dietro `display:none` contava comunque come "secondo h1",
facendo fallire il check `titoli` anche quando un solo h1 era davvero percepibile.

**Cosa misura ora**: `h1Count` = numero di `<h1>` **esposti** (non nascosti da
`display:none`/`visibility:hidden`/attributo `[hidden]`/un antenato con `aria-hidden="true"`,
verificato con `Element.checkVisibility({checkVisibilityCSS:true})` più un controllo esplicito
su `[hidden]`/`[aria-hidden="true"]` negli antenati). Il conteggio grezzo nel DOM resta
disponibile nel report (`numeroH1TotaliNelDom`) come nota informativa quando differisce da
quello esposto — non fa fallire nulla da solo.

**Perché**: coerente con come uno screen reader/axe-core leggono davvero la pagina — un
elemento non esposto all'albero di accessibilità non esiste ai fini di "un solo elemento
dominante per pagina". Il criterio "nel DOM" era un proxy comodo da misurare ma misurava la
cosa sbagliata.

**Nota per confrontare con la baseline**: la baseline del passo 1
(`baseline_narratours.md`, misurata 09/09/2026) riporta "h1: 2" su **tutte e 6** le pagine
col criterio VECCHIO (conteggio grezzo). Non è detto che tutte falliscano ancora col criterio
nuovo — su `yourservice-it` bonificato, col criterio nuovo, il pavimento misura **1 h1
esposto** (chiuso). Le 4 pagine tour e la pagina bundle non sono state rimisurate in questo
passo: il loro "h1: 2" in baseline va riletto con questa nota, non preso per buono senza
riverificare.

**CSS orfano trovato, non rimosso (fuori dal perimetro React specifico).** Dentro
`blocco_body_mobile_per_host.html`, oltre a `#hero-root{...}` (rimosso, orfano diretto della
rimozione React), esiste un'altra famiglia di CSS orfano preesistente e indipendente:
`.hero`, `.hero-card`, `.hero-logo`, `.hero-badge`, `.hero-cards`, `.calc-note` — nessun
markup corrispondente nel file (verificato: nessun `class="hero"` o simile nel body).
Probabilmente una hero più vecchia, precedente sia al tentativo React sia all'hero v3 finale.
Non rimossa in questa bonifica (non era nel perimetro dichiarato nel piano); candidato per un
prossimo micro-intervento di pulizia, a basso rischio (nessun markup la referenzia, quindi
nessun impatto visivo atteso).

## 10. Fedeltà locale/live — fattori di divergenza noti (10/09/2026)

Emersi confrontando ripetutamente ricomposizione locale e pagina live durante la Fase B.
Servono a leggere correttamente il test di fedeltà N.2 (Fase C, sull'anteprima GHL): una
differenza tra locale e anteprima **non è automaticamente un bug della bonifica** se rientra
in uno di questi fattori noti — ma nemmeno va scartata senza controllare quale dei due casi
sia.

- **CSS di sezione GHL assente in locale.** Il meccanismo che su GHL nasconde/mostra intere
  sezioni per viewport (es. la hero desktop vs mobile prima del fix di questa Fase B) vive a
  livello di builder/piattaforma, non nei blocchi Code — non è nel repo, non riproducibile in
  locale. Dopo questa bonifica i blocchi hero hanno il proprio `display:none` esplicito quindi
  non dipendono più da questo meccanismo, ma altre sezioni duplicate desktop/mobile (vedi
  "Duplicazione desktop/mobile del markup" sopra) sì.
- **Cloudflare Turnstile — rumore non deterministico.** GTranslate e/o il form GHL innescano
  una sfida Turnstile che in questo ambiente di sviluppo genera un numero variabile di
  richieste/errori console da un run all'altro (osservato: peso stabile entro poche decine di
  KB, ma "richieste totali" ed "errori console" oscillano di alcune unità run su run anche a
  parità di codice — vedi §8 sopra e la tabella di confronto omogeneo nel report di consegna).
  Non usare un singolo run come prova di regressione: guardare il trend su più run, o il
  peso in KB che è il numero stabile.
- **Tracking code globale non disponibile nel repo.** Il CSS/JS del Head/Body tracking code
  di GHL (Settings > Tracking & scripts) non è salvato da nessuna parte nel repo — solo i
  suoi effetti misurati (colori, font, breakpoint) in `baseline_narratours.md`. La
  ricomposizione locale non lo include: funziona perché i blocchi sono scritti per essere
  autosufficienti (variabili CSS scoped alla sezione, non su `:root` — verificato in
  `blocco_hero_mobile_v3.html`), ma un font o una regola che dipendesse davvero dal tracking
  code globale non comparirebbe in locale.

---

## DA VERIFICARE residui

- Esiste "Duplica pagina" nel builder? (non osservato nella ricognizione — necessario per
  portare una pagina Website dentro un Funnel quando si arriverà al test A/B, §5)
- Il meta `noindex` inserito a mano nell'Header Tracking di una pagina arriva davvero
  nell'head servito? (§2, regola 4 — lo verifica il ciclo visivo al primo uso)
- L'URL `/preview/` riflette la bozza salvata anche quando la pagina pubblicata è diversa,
  o in qualche caso mostra il pubblicato? (si verifica col primo pezzo reale)
- Inter (`!important` nel CSS globale) non vince nel computed style misurato sulle pagine
  tour, che rendono Playfair Display/DM Sans (§1 — debito tecnico). Spiegazione candidata
  registrata: specificità di classe nei blocchi batte `body *` a parità di `!important`. Da
  confermare guardando un selettore reale alla prima bonifica — non indagare prima.

## Nota fuori struttura

`CANTIERE_Designer.md` (il documento di progettazione del cantiere) è stato salvato in
`knowledge/CANTIERE_Designer.md` il 09/09/2026 (era il pezzo mancante segnalato a fine passo
1 — nessuna modifica al contenuto ricevuto).
