# TEMPLATE_BRIEF — struttura fissa dei brief per Claude Code

**v1 — 12 settembre 2026, cantiere Argo — il ponte, passo 1.** Non esisteva
nel repo un file che descrivesse la forma dei brief che Leonardo scrive a
mano per aprire una sessione di Claude Code: questo documento la fissa,
usando come riferimento concreto il brief che Leonardo ha dato per la
sessione che ha costruito il comando `/brief` stesso. `argo/voce.py:
genera_brief()` la implementa: lo scheletro qui sotto (titolo, "Plan mode
obbligatorio", Vincoli standard, la riga su chi ha ragione in caso di
conflitto) è composto in Python, sempre uguale — solo Contesto, Obiettivo
e Criterio di chiusura sono scritti dall'LLM a partire dal contesto
raccolto sul cantiere.

## Struttura

```
<nome del cantiere, esatto>

Plan mode obbligatorio.

## Contesto

<elenco puntato di cosa leggere prima — solo file/sezioni/comandi citati
alla lettera nel contesto raccolto>

Leggi questi file prima di scrivere codice. Se qualcosa nel repo
contraddice questo brief, ha ragione il repo: fermati e dimmelo invece
di procedere.

## Obiettivo

<uno o due paragrafi: il prossimo passo del cantiere. Se il contesto
raccolto non basta per dirlo con certezza: "Da precisare con Leonardo: ..."
invece di un obiettivo plausibile inventato>

## Vincoli

- Se serve un sub-agent per una parte del lavoro, lancialo e passa comunque
  dal guardrail (subagent guardrail-review) sul diff prima di committare.
- Niente git push: lo fa Leonardo a mano.
- La suite di test deve restare verde.
- Se tocchi un componente condiviso, una tabella o un file di
  worker/loop.py, lancia scripts/panoptes/impatti.py prima di modificare;
  scripts/panoptes/verifica_mappa.py deve uscire 0 prima del push.
- Aggiorna STATO.md (blocco ## CANTIERI + nota di sessione) a fine
  sessione.

## Criterio di chiusura

<uno o due paragrafi: come si riconosce che questo passo è concluso, dagli
stessi dati. Stessa regola anti-invenzione dell'Obiettivo>
```

## Perché questa forma e non un'altra

- **"Plan mode obbligatorio." è sempre la prima riga dopo il titolo.**
  Leonardo dirige, Claude Code implementa in plan mode — regola già scritta
  in `knowledge/argo/USER.md`, non specifica del ponte.
- **Contesto elenca cosa leggere PRIMA di scrivere codice**, mai un
  riassunto di cosa fare — quello è l'Obiettivo. Chiude sempre con la
  stessa riga fissa ("ha ragione il repo"): un brief nasce da uno stato
  osservato in un momento preciso, il repo può essere cambiato nel
  frattempo o il brief può semplicemente sbagliare un dettaglio — vince
  sempre quello che Claude Code trova leggendo, non quello che il brief
  presume.
- **Vincoli è testo fisso, mai generato dal modello.** Sono le stesse
  cinque regole ogni volta (sub-agent guardrail, niente git push, suite
  verde, verifica_mappa.py, STATO.md aggiornato) — farle scrivere all'LLM
  ogni volta rischierebbe una parafrasi che perde un pezzo silenziosamente,
  proprio il tipo di errore che l'anti-invenzione di questo cantiere vuole
  evitare.
- **Criterio di chiusura è una domanda a cui la sessione futura deve poter
  rispondere da sola**, non un elenco di task — coerente con l'uso reale
  osservato in `STATO.md` (es. "il test di accettazione ha esito pieno",
  non "fare X, Y, Z").
- **Niente domande finali nel testo del brief** — stessa regola già in
  vigore per orienta/instrada/avvisa in `argo/voce.py`, qui applicata a un
  destinatario diverso (Claude Code, non Leonardo): un brief è un mandato
  scritto, non l'apertura di una conversazione.
