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
- **Head/footer per pagina**: builder > icona `</>` "Tracking Code" > tab "Header Tracking"
  / "Footer Tracking".

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
   `<meta name="robots" content="noindex">` inserito a mano nel Header Tracking della
   pagina. [DA VERIFICARE al primo uso: che il meta compaia davvero nell'head servito — il
   ciclo visivo lo controlla.]
5. **Niente modifiche al sito live in questo cantiere**: ogni lavoro avviene su pagina di
   prova o su bozza salvata e mai pubblicata. Pubblicare è sempre e solo un'azione manuale
   di Leonardo, fuori dal cantiere.

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
