# Baseline reale — narra-tours.com (misurata il 09/09/2026)

Numeri estratti da Playwright headless (Chromium) sul VPS di produzione, sulle 6 pagine
pubbliche indicate nel brief. Nessun login, nessuna pagina privata. Fonte dei comandi:
`.claude/skills/designer/scripts/{cattura,pavimento}.mjs`. Il sito è dietro
Cloudflare/GoHighLevel: verificato che le pagine servite sono contenuto reale (HTTP 200,
`cf-cache-status: HIT`, nessuna challenge/captcha nello screenshot di prova).

## Peso e prestazioni reali per pagina

| Pagina | KB totali | Richieste | KB immagini | Primo render (ms) |
|---|---:|---:|---:|---:|
| tour-blood-glory-ancientrome | 8169 | 100 | 5984 | 508 |
| tour-vatican-city | 8566 | 101 | 5922 | 1136 |
| tour-power-sins | 8180 | 94 | 5908 | 1972 |
| tour-trastevere-rebel | 8453 | 100 | 5813 | 1356 |
| bundle-essential-tours | 2777 | 83 | 1121 | 1316 |
| yourservice-it | 6053 | 330 | 728 | 756 |

Le 4 pagine tour singole pesano tutte 8-8.5MB, il 70-73% in immagini: è il peso dominante.
`yourservice-it` è più leggera in immagini ma ha 330 richieste (3x le altre) — probabile
accumulo di script terzi/tracking su una pagina orientata alla conversione host, non tour.
`bundle-essential-tours` è la più leggera (2.7MB).

**KB = byte trasferiti "on the wire" (post-compressione, da `request.sizes()` di Playwright,
non byte decodificati in memoria)**. Primo render = `first-contentful-paint` della pagina,
non un audit Lighthouse (Lighthouse non è installato in questo progetto — vedi § Ciclo
visivo in `narratours.md`).

## Font realmente serviti

Tutte le pagine: **DM Sans** + **Playfair Display**, in formato **woff2**, serviti da
**fonts.gstatic.com** (Google Fonts) — confermato: corrisponde alla coppia dichiarata
Playfair Display + DM Sans. Presente anche **Font Awesome 5** (icone, free + brands) su
tutte le pagine. Costo font: **135 KB** sulle pagine tour/bundle, **285 KB** su
`yourservice-it` (carica anche la famiglia **Inter**, non dichiarata altrove — pagina
diversa, orientata all'host non al turista).

## Palette realmente usata vs dichiarata

Dichiarata: `#0f0a06` `#1a1410` `#faf9f6` `#c49a3c` `#e8c46a` `#6ee7a0`

Campionati i colori calcolati (computed style) di `body`, `h1`, `h2`, `button`, CTA e prezzo
su ogni pagina. **Nota sul metodo**: il campionamento prende il primo elemento che
corrisponde al selettore (es. il primo `button` del DOM può essere l'hamburger di menu, non
una CTA) — è rappresentativo, non esaustivo. Le violazioni di contrasto trovate da axe-core
(sotto) sono il segnale più affidabile su dove il contrasto è davvero un problema.

- **`#0f0a06` confermato esatto** — sfondo body sulle 4 pagine tour singole.
- **`#faf9f6` confermato esatto** — colore testo body su `bundle-essential-tours`; sfondo
  della CTA (`[class*="cta"]`) sulle pagine tour.
- **`#c49a3c` confermato esatto** — sfondo del bottone CTA (`a[class*="btn"]` e
  `[class*="cta"]`) su `yourservice-it`.
- **`#e8c46a` e `#6ee7a0` non osservati** nei selettori campionati — possono comparire su
  badge, hover, accenti non intercettati da questo campionamento. Non confermati né
  smentiti: da verificare a vista quando si lavorerà su quelle pagine.
- **Divergenza reale**: il testo su `body`/`h1`/`h2` delle 4 pagine tour calcola
  `rgb(26,23,20)` = `#1a1714`, non `#1a1410` dichiarato — differenza piccola (canali
  verde/blu) ma non nulla. Segnalata come divergenza, non appianata.
- **`bundle-essential-tours` inverte lo schema** delle altre 3 pagine tour: testo chiaro
  (`#faf9f6`) su sfondo scuro (`#1c120a`, vicino a `#1a1410`), mentre le altre hanno testo
  scuro su sfondo quasi nero (`#0f0a06`). Divergenza tra pagine dello stesso tipo, non solo
  rispetto al documento.

## Verdetto del pavimento per pagina

Contrasto/console/titoli **falliscono su tutte e 6 le pagine**; breakpoint **passa su
tutte**. Questo è il termine di paragone dichiarato nel brief: il Designer dovrà fare meglio.

| Pagina | Verdetto | Contrasto (crit/serious/moderate/minor) | Console (errori/pagina/risorse fallite) | H1 | Livello titoli saltato |
|---|---|---|---|---:|---|
| tour-blood-glory-ancientrome | FAIL | 4/52/84/9 | 6/0/2 | 2 | sì |
| tour-vatican-city | FAIL | 4/56/95/9 | 8/0/4 | 2 | sì |
| tour-power-sins | FAIL | 4/56/95/9 | 6/0/3 | 2 | sì |
| tour-trastevere-rebel | FAIL | 4/56/95/9 | 8/0/4 | 2 | sì |
| bundle-essential-tours | FAIL | 2/44/64/9 | 6/0/2 | 2 | no |
| yourservice-it | FAIL | 1/65/55/0 | 14/4/5 | 2 | sì |

Ogni pagina ha **2 `h1`**, mai 1 — violazione sistematica del "un solo elemento dominante",
probabile duplicazione tra versione mobile/desktop nel DOM del builder GoHighLevel (non
verificato a fondo, solo osservato). Report JSON completi in
`.claude/skills/designer/output/*_pavimento_*.json`.

**Correzione (11/09/2026) — la colonna H1 di questa tabella è un falso positivo, non un bug
delle pagine.** Il conteggio "2" veniva dai nodi grezzi del DOM (`querySelectorAll('h1')`),
senza filtrare per visibilità: su `yourservice-it`, verificato che i due `<h1>` sono le
varianti desktop/mobile della stessa hero, e GHL le nasconde reciprocamente con un
`display:none` di piattaforma reale (classi `.desktop-only`/`.tablet-hide`/`.mobile-only`,
confine 767/768px — vedi `modalita/narratours.md` §2), non con un semplice collasso 0×0.
Con un criterio che conta gli h1 **esposti** (stesso di `pavimento.mjs` dopo la correzione
del 10/09/2026), `yourservice-it` misura **1 h1 esposto a ogni larghezza testata**, sulla
pagina live intatta, prima di qualunque intervento del cantiere Designer. Il "problema" che
giustificava un fix in Fase B non esisteva: il fix aggiunto (soglia 861px) ha invece
introdotto una vera finestra morta 768-860px, poi rimosso in Fase C. Le altre 5 pagine (le 4
tour + il bundle) **non sono state rimisurate** con il criterio nuovo: questo "2" resta da
verificare per loro, non da assumere come bug reale solo perché scritto qui.

## Breakpoint effettivi (dalle media query nei CSS serviti)

- **4 pagine tour singole**: identiche — `380 480 640 760 767 768 860 861 900 979 980 991
  1024 1100 1200` px. Le coppie (767/768, 860/861, 979/980) sono tipiche di un framework a
  min/max-width accoppiati (verosimilmente lo stack del builder GoHighLevel).
- **`bundle-essential-tours`**: quasi identica ma manca la coppia 767/768 e 860/861, ha
  980/991 invece di 979/980, aggiunge 1280 in cima.
- **`yourservice-it`**: set diverso, aggiunge 340/550/820 e include un valore `10000` px —
  quasi certamente un trucco CSS per disattivare una regola (`min-width:10000px` non scatta
  mai), non un breakpoint reale. Da ignorare come breakpoint, riportato per trasparenza.

## Struttura ricorrente (scheletro delle 4 pagine tour)

Sequenza `h2` **identica sulle 4 pagine tour singole** (blood-glory, vatican-city,
power-sins, trastevere-rebel):

1. "You only have a few days in Rome" (compare due volte nel DOM — verosimilmente varianti
   mobile/desktop non deduplicate)
2. "Where to"
3. "What you pay for"
4. "What you get for free"
5. "Google reviews. Verified."
6. "Rome is waiting. Your story starts now."

Questo è lo scheletro del futuro template tour. `bundle-essential-tours` condivide
"Where to"/recensioni/chiusura ma sostituisce le sezioni centrali con "3 tours. One price.",
"What you get with every tour", "Premium All-Access Pass" — variante coerente, non
un'anomalia. `yourservice-it` ha una struttura completamente diversa (pagina di
reclutamento host, non tour) con 21 sezioni.
