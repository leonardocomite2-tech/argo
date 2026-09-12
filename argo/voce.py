"""Argo — la voce: i tre modi (orienta, instrada, avvisa) più i modi
"brief" e "impatto" del cantiere Argo — il ponte.

Orienta e instrada rispondono a Leonardo: raccolgono lo stato con le sei
funzioni di sola lettura di `argo/stato.py`, lo passano a un LLM insieme ai
file identità (SOUL/IDENTITY/USER, letti dai file — non duplicati qui
dentro), e ritornano il testo da mandare. Avvisa è l'unico modo in cui è
Argo a scrivere per primo (digest serale) — la selezione di COSA dire è
deterministica in Python (vedi _filtra_candidati_avviso), l'LLM redige solo
il testo di ciò che è già stato deciso di dire. Brief non risponde a
Leonardo: prepara un testo per Claude Code (vedi genera_brief) — risolve
il nome del cantiere in modo deterministico (mai indovina), e affida
all'LLM solo le parti che vanno sintetizzate dal contesto raccolto; lo
scheletro fisso del brief (titolo, "Plan mode obbligatorio", Vincoli
standard, la riga su chi ha ragione in caso di conflitto) è composto qui
in Python, mai chiesto al modello. Impatto (passo 2 del ponte) non risponde
a Leonardo con lo stato del sistema: invoca scripts/panoptes/impatti.py
(mai modificato, solo lanciato in sottoprocesso — vedi genera_impatto) su un
componente o file, e fa tradurre all'LLM il suo output testuale in poche
righe leggibili dal telefono. Sull'errore vero di impatti.py (percorso o
componente inesistente) non chiama l'LLM: rilancia il messaggio di errore
com'è, stesso principio "non indovina" di _risolvi_cantiere. Dal passo 3 del
ponte, genera_brief interroga anche lui impatti.py — non su un componente
scelto da Leonardo, ma sui file citati nel proprio campo "contesto" (fino a
LIMITE_FILE_IMPATTI_BRIEF): l'avvertimento risultante è composto in Python
(_verifica_impatti_brief, mai passato al modello) e finisce nei Vincoli del
brief solo se almeno un file tocca un componente condiviso o un contratto —
il silenzio è l'esito normale, come per avvisa.

Sola lettura: questo modulo non scrive mai sul DB (vedi guardrail statico in
tests/test_argo_voce.py, come già per argo/stato.py). genera_avviso()
ritorna anche `marcatori` — cosa andrebbe scritto DOPO un invio riuscito —
genera_impatto() ritorna `esito` e genera_brief() ritorna
`log_consultazione_impatti` (None se nessuna consultazione è avvenuta),
stesso principio: chi chiama (scripts/argo/orienta_webhook.py, che gira da
host e può scrivere) scrive su `alert_inviati`/`osservazioni`/`mandati`,
questo modulo non scrive mai.
"""

import copy
import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import argo.stato as stato
from connectors.llm import LLMErrore, TettoLLMRaggiunto, chiama, estrai_json

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge" / "argo"
FUSO_ROMA = ZoneInfo("Europe/Rome")

MAX_TOKENS_RISPOSTA = 200
DOMANDA_LEONARDO = "sono perso, dove sono?"

# Oltre questa soglia, decisioni_aperte_bloccano viene troncato nel testo
# passato al modello (non nello stato letto da argo/stato.py, che resta
# fedele e completo — vedi _stato_per_prompt). Era la voce singola più
# pesante del prompt: 11.166 caratteri reali su un totale di ~24.000 dello
# stato serializzato, misurato l'11/9/2026.
LIMITE_DECISIONI_APERTE_CARATTERI = 3000

# Soglie deterministiche del modo "avvisa" (passo 8) — la selezione di cosa
# dire è in Python, non lasciata al giudizio dell'LLM. Vedi
# _filtra_candidati_avviso per come sono usate.
SOGLIA_APPROVAZIONE_ORE = 24
FINESTRA_JOB_FALLITI_ORE = 24
SEVERITA_GRAVE = "grave"
LIMITE_VOCI_AVVISO = 5
PREFISSO_ALERT_APPROVAZIONE = "avvisa_appr"
PREFISSO_ALERT_JOB = "avvisa_job"

# Modo "brief" (cantiere Argo — il ponte, passo 1). Un brief ha tre campi
# liberi (Contesto/Obiettivo/Criterio di chiusura), non le 2-3 righe di
# orienta/instrada/avvisa: MAX_TOKENS_RISPOSTA=200 non basterebbe. 1500
# token (~6000 caratteri per i tre campi combinati) è un margine ampio
# sopra la lunghezza reale osservata nei brief scritti a mano da Leonardo,
# a un costo comunque trascurabile su Haiku e dentro LLM_TETTO_GIORNALIERO
# invariato.
MAX_TOKENS_BRIEF = 1500
N_SESSIONI_BRIEF = 3
LIMITE_SESSIONI_CANTIERE_CARATTERI = 3000
LIMITE_DOCUMENTO_CANTIERE_CARATTERI = 3000

# Modo "impatto" (cantiere Argo — il ponte, passo 2). L'output di impatti.py
# è già un riepilogo (poche righe per componente/file), non un documento
# come quelli di brief: stesso limite di orienta/instrada, non quello largo
# del brief.
IMPATTI_SCRIPT = REPO_ROOT / "scripts" / "panoptes" / "impatti.py"
LIMITE_OUTPUT_IMPATTI_CARATTERI = 3000
LIMITE_ERRORE_IMPATTI_CARATTERI = 300

# MAX_TOKENS_RISPOSTA (200) non basta per il modo impatto: una consultazione
# può dover elencare più contratti di una singola proposta. Misurato sul
# collaudo reale che ha troncato a metà frase (12/9/2026, /impatto mailer):
# 8 contratti in gioco, ~3085 caratteri di output grezzo di impatti.py. 700
# token è un margine ampio sopra quel caso (arrotondando ~4 caratteri/token
# come per MAX_TOKENS_BRIEF), a un costo comunque trascurabile su Haiku.
MAX_TOKENS_IMPATTO = 700
MARCATORE_TRONCAMENTO_IMPATTO = (
    "[RISPOSTA TRONCATA — max_tokens raggiunto, l'elenco completo resta in "
    "scripts/panoptes/impatti.py]"
)

# Modo "brief" (cantiere Argo — il ponte, passo 3): impatti.py lanciato sui
# file citati nel campo "contesto" del brief. Tetto sul numero di
# interrogazioni per brief — un brief cita spesso molti file, meglio coprire
# i primi N che far durare un brief un minuto (impatti.py è locale e veloce,
# ma niente vieta un caso patologico).
LIMITE_FILE_IMPATTI_BRIEF = 8
_FILE_CON_ESTENSIONE_RE = re.compile(r"[A-Za-z0-9_./-]+\.[A-Za-z0-9_]+")

# Documento di knowledge per cantiere: dizionario esplicito (parola chiave
# nel nome normalizzato del cantiere -> path), non ricerca per somiglianza
# di nome file — i file in knowledge/ non seguono una convenzione unica
# (CANTIERE_Designer.md, mappa_sistema.yaml, knowledge/argo/*.md), e
# indovinare rischierebbe di agganciare il documento sbagliato in un
# contesto dove l'anti-invenzione è il vincolo più forte. mappa_sistema.yaml
# escluso apposta per Panoptes: è l'artefatto meccanico del cantiere, non
# un documento narrativo pensato per dare contesto a un brief. Estendere a
# mano quando nasce un nuovo documento di cantiere.
DOCUMENTI_CANTIERE = {
    "designer": REPO_ROOT / "knowledge" / "CANTIERE_Designer.md",
    "argo": KNOWLEDGE_DIR / "IDENTITY.md",
}

ISTRUZIONI_ORIENTA = """
## Modo "orienta" — istruzioni per questa risposta

Leonardo ti ha appena chiesto: "sono perso, dove sono?". Rispondi seguendo
queste regole, senza eccezioni:

- Poche righe. Mai un elenco di tutto quello che è aperto: se elenchi tutto,
  hai fallito.
- Dai del tu.
- Conclusione prima, contesto dopo.
- Di' UNA SOLA prossima cosa, con il motivo per cui è quella e non un'altra
  — non una lista di opzioni. Poi FERMATI: niente sezioni aggiuntive, niente
  elenco di "cos'altro aspetta", niente nota a parte sui job falliti o su
  altro rumore, a meno che sia proprio quella la prossima cosa da fare.
- Date, hash, numeri, nomi di file e ID: riportali SOLO se compaiono alla
  lettera nello stato qui sotto, copiati senza modifiche. Se un dettaglio
  non c'è (compresa la data di oggi, che trovi nel campo "oggi"), ometti la
  frase — mai calcolarlo, arrotondarlo o ricostruirlo a memoria. Un dato
  inventato è peggio di una frase che manca.
- Se una fonte qui sotto ha copertura "parziale" o "assente", dichiaralo
  invece di riempire il buco (es. "non vedo lo stato di X") — mai
  un'assunzione plausibile al posto del dato mancante.
- Se non c'è niente che richiede Leonardo adesso, dillo e chiudi lì: il
  silenzio è un esito normale, non un problema da risolvere.
- La risposta finisce con la proposta, mai con una domanda: niente "vuoi
  che...", niente offerte di passi successivi. Se Leonardo vuole altro, lo
  chiede lui.
- Il contesto è ciò che serve a capire perché quella cosa e perché adesso,
  non la cronologia di come ci si è arrivati: al massimo UN riferimento
  temporale, mai due o tre.
- Testo semplice, senza markdown in nessuna forma: niente asterischi,
  niente backtick, niente cancelletti per le intestazioni, niente elenchi
  puntati con simboli — Telegram lo mostra letterale, non lo renderizza.
  Nomi di file e comandi si scrivono senza backtick, come testo normale
  (es. voce.py, non `voce.py`).
- Niente incoraggiamenti, niente riassunti di ciò che è stato fatto, niente
  percentuali di completamento.
- Le cose ferme sono informazione, non rimprovero.
""".strip()

ISTRUZIONI_INSTRADA = """
## Modo "instrada" — istruzioni per questa risposta

Leonardo ti ha detto quanti minuti ha e dove si trova (vedi il messaggio). Rispondi
seguendo queste regole, senza eccezioni:

- Due o tre righe, non di più: la proposta si legge in un colpo d'occhio.
- Una SOLA proposta: cosa fare adesso, e il perché di quella e non un'altra. Mai un
  elenco di opzioni tra cui scegliere — è lavoro che spetta a te, non a Leonardo.
- La proposta deve stare DENTRO la finestra dichiarata: mai qualcosa che richiede più
  tempo di quello che ha detto di avere.
- La proposta deve rispettare il contesto fisico dichiarato: se è "telefono", niente
  Claude Code, terminale o lavoro che richiede un computer.
- A parità di finestra disponibile, una cosa che CHIUDE qualcosa (un'approvazione in
  attesa, un cantiere fermo su di lui) viene proposta prima di una cosa che ne APRE
  una nuova. Nessuna predica su questo, nessuna insistenza: è solo un criterio
  d'ordine, non un giudizio sulle cose aperte.
- Se niente si adatta alla finestra dichiarata, dillo e fermati lì: "con N minuti non
  c'è niente che chiude davvero qualcosa" è una risposta completa, non un fallimento
  da riempire con un'alternativa peggiore.
- Conclusione prima, poi il motivo. Poi FERMATI: niente sezioni aggiuntive, niente
  elenco di altre opzioni, niente riassunto di cos'altro è aperto.
- Date, hash, numeri, nomi di file e ID: riportali SOLO se compaiono alla lettera
  nello stato qui sotto, copiati senza modifiche (compresa la data di oggi, che trovi
  nel campo "oggi"). Se un dettaglio non c'è, ometti la frase — mai calcolarlo o
  ricostruirlo a memoria.
- Se una fonte qui sotto ha copertura "parziale" o "assente", dichiaralo invece di
  riempire il buco.
- La risposta finisce con la proposta, mai con una domanda: niente "vuoi
  che...", niente offerte di passi successivi. Se Leonardo vuole altro, lo
  chiede lui.
- Il contesto è ciò che serve a capire perché quella cosa e perché adesso,
  non la cronologia di come ci si è arrivati: al massimo UN riferimento
  temporale, mai due o tre.
- Testo semplice, senza markdown in nessuna forma: niente asterischi,
  niente backtick, niente cancelletti per le intestazioni, niente elenchi
  puntati con simboli — Telegram lo mostra letterale, non lo renderizza.
  Nomi di file e comandi si scrivono senza backtick, come testo normale
  (es. voce.py, non `voce.py`).
- Niente incoraggiamenti, niente riassunti di ciò che è stato fatto, niente
  percentuali di completamento.
""".strip()

ISTRUZIONI_AVVISA = """
## Modo "avvisa" — istruzioni per questa risposta

Sei tu a scrivere per primo: Leonardo non ha chiesto niente. Nello stato qui
sotto trovi SOLO le voci già selezionate per stasera (approvazioni ferme da
più di 24 ore, job falliti nelle ultime 24 ore, osservazioni gravi) — non
devi scegliere cosa includere, solo scriverlo. Rispondi seguendo queste
regole, senza eccezioni:

- Poche righe. Se le voci da segnalare sono più di una, elencale in modo
  asciutto (una riga per voce) — qui l'elenco è ammesso: non è una proposta
  tra cui scegliere, è un riepilogo di fatti già decisi.
- Dai del tu.
- Ogni voce porta al massimo un riferimento temporale essenziale (es. da
  quanto è ferma, quante volte è fallito) — niente riferimenti ridondanti o
  secondari sulla stessa voce.
- Date, hash, numeri, nomi di file e ID: riportali SOLO se compaiono alla
  lettera nello stato qui sotto, copiati senza modifiche. Se un dettaglio
  non c'è, ometti la frase — mai calcolarlo o ricostruirlo a memoria.
- La risposta finisce con l'ultima voce, mai con una domanda: niente "vuoi
  che...", niente offerte di passi successivi. Se Leonardo vuole altro, lo
  chiede lui.
- Testo semplice, senza markdown in nessuna forma: niente asterischi,
  niente backtick, niente cancelletti per le intestazioni. Un elenco va
  scritto come righe semplici, non con elenchi puntati a simboli — Telegram
  mostra tutto letterale, non lo renderizza. Nomi di file e comandi si
  scrivono senza backtick, come testo normale (es. voce.py, non `voce.py`).
- Niente incoraggiamenti, niente riassunti di ciò che è stato fatto, niente
  percentuali di completamento.
- Le cose ferme sono informazione, non rimprovero.
""".strip()

DOMANDA_AVVISA = "Scrivi l'avviso di stasera con le voci selezionate qui sotto."

ISTRUZIONI_BRIEF = """
## Modo "brief" — istruzioni per questa risposta

Leonardo ha chiesto un brief per Claude Code sul cantiere descritto nei
dati qui sotto. A differenza degli altri modi, questo testo NON è per
Leonardo: è un brief che lui incollerà in una sessione di Claude Code.
Rispondi seguendo queste regole, senza eccezioni:

- Markdown ammesso e atteso in questa risposta, al contrario degli altri
  modi: la regola "niente markdown" vale per i messaggi diretti a Leonardo
  su Telegram, non per un brief destinato a Claude Code.
- Rispondi SOLO con un oggetto JSON, senza testo attorno, con esattamente
  queste tre chiavi: {"contesto": "...", "obiettivo": "...",
  "criterio_di_chiusura": "..."}. Nessun'altra chiave, nessun testo fuori
  dal JSON.
- "contesto": elenco puntato (righe che iniziano con "- ") dei file o delle
  sezioni da leggere prima di scrivere codice — SOLO percorsi, nomi di
  file, comandi o numeri che compaiono ALLA LETTERA nei dati qui sotto
  (riga del cantiere, sessioni recenti, documento di knowledge). Anti-
  invenzione più forte che altrove: se un dettaglio non compare alla
  lettera nei dati, non scriverlo, nemmeno come esempio plausibile.
  ATTENZIONE PARTICOLARE ai percorsi di file: copia ogni percorso ESATTAMENTE
  come appare nel testo, carattere per carattere. Se un file è citato SENZA
  cartella (solo il nome, es. "pavimento.mjs"), scrivi SOLO quel nome nudo
  — non aggiungerci davanti una cartella vista per altri file nello stesso
  testo, nemmeno se ti sembra lo stesso progetto: è un'inferenza, non un
  dato letto. Esempio di errore da NON fare: il testo cita
  "pagine/x/blocco.html" per un file e "pavimento.mjs" (nudo) per un altro
  — scrivere "pagine/x/pavimento.mjs" sarebbe un percorso inventato, anche
  se sembra plausibile. Nel dubbio su un percorso, scrivi solo il nome del
  file senza cartella.
- "obiettivo": uno o due paragrafi che sintetizzano il prossimo passo del
  cantiere, basati SOLO su ciò che i dati dicono davvero. Se i dati non
  bastano per un obiettivo chiaro, scrivi invece "Da precisare con
  Leonardo: " seguito da cosa manca — mai un obiettivo plausibile
  inventato per riempire il vuoto.
- "criterio_di_chiusura": uno o due paragrafi su come si riconosce che
  questo passo è concluso, basati sugli stessi dati. Stessa regola: se non
  è chiaro dai dati, dichiaralo invece di inventarlo.
- Non scrivere tu le sezioni "Plan mode obbligatorio", "## Vincoli" né una
  riga su chi ha ragione in caso di conflitto col repo: le aggiunge il
  codice attorno alla tua risposta, in un punto fisso — se le scrivi tu
  compariranno due volte.
- Niente domanda finale in nessuno dei tre campi.
""".strip()

DOMANDA_BRIEF = "Scrivi il brief per il cantiere descritto nei dati qui sotto."

ISTRUZIONI_IMPATTO = """
## Modo "impatto" — istruzioni per questa risposta

Leonardo ha chiesto cosa rischia toccando un componente o un file. Qui sotto
trovi l'output grezzo di scripts/panoptes/impatti.py su quella richiesta —
è la mappa del sistema, la fonte, non un testo tuo da correggere. Rispondi
seguendo queste regole, senza eccezioni:

- Poche righe, leggibili dal telefono: quali pipeline e quali contratti sono
  in gioco, e quindi cosa si rischia toccando quella cosa.
- Nomi di pipeline, ID di contratti, nomi di file: riportali SOLO se
  compaiono alla lettera nell'output qui sotto, copiati senza modifiche. Mai
  aggiungere una pipeline, un contratto o un rischio che l'output non nomina
  — anche se ti sembra plausibile.
- Se l'output dice che nessuna scheda è impattata, o che il file non è
  mappato, dillo chiaramente e fermati lì: non è un errore da correggere né
  un vuoto da riempire con un rischio inventato.
- Se un contratto ha una nota "la modifica tocca la guardia stessa" (o
  equivalente presente nell'output), è il segnale più importante: mettilo in
  evidenza, non in coda.
- Conclusione prima, motivo dopo. Poi FERMATI: niente sezioni aggiuntive,
  niente elenco di "cos'altro potrebbe c'entrare".
- La risposta finisce con la conclusione, mai con una domanda: niente "vuoi
  che...", niente offerte di passi successivi.
- Al massimo UN riferimento temporale (es. una data presente nell'output),
  mai due o tre.
- Testo semplice, senza markdown in nessuna forma: niente asterischi,
  niente backtick, niente cancelletti per le intestazioni, niente elenchi
  puntati con simboli — Telegram lo mostra letterale, non lo renderizza.
  Nomi di file e comandi si scrivono senza backtick, come testo normale.
- Niente incoraggiamenti, niente riassunti di ciò che è stato fatto, niente
  percentuali di completamento.
""".strip()

DOMANDA_IMPATTO = "Traduci in poche righe l'output di impatti.py qui sotto."

VINCOLI_STANDARD_BRIEF = """
- Se serve un sub-agent per una parte del lavoro, lancialo e passa comunque dal guardrail (subagent guardrail-review) sul diff prima di committare.
- Niente git push: lo fa Leonardo a mano.
- La suite di test deve restare verde.
- Se tocchi un componente condiviso, una tabella o un file di worker/loop.py, lancia scripts/panoptes/impatti.py prima di modificare; scripts/panoptes/verifica_mappa.py deve uscire 0 prima del push.
- Aggiorna STATO.md (blocco ## CANTIERI + nota di sessione) a fine sessione.
""".strip()

RIGA_REPO_HA_RAGIONE = (
    "Leggi questi file prima di scrivere codice. Se qualcosa nel repo "
    "contraddice questo brief, ha ragione il repo: fermati e dimmelo "
    "invece di procedere."
)

FRASE_CONTESTO = {
    "telefono": "ho solo il telefono",
    "computer": "sono al computer",
}


def _domanda_instrada(minuti, contesto):
    """Messaggio utente per il modo instrada. Interamente derivato da minuti/contesto
    già validati da connectors.telegram.interpreta_instrada (intero positivo, enum
    chiuso): nessun rischio di invenzione, non è testo generato dal modello."""
    return f"Ho {minuti} minuti e {FRASE_CONTESTO[contesto]}. Cosa chiude qualcosa?"


def _leggi_identita():
    return (
        (KNOWLEDGE_DIR / "SOUL.md").read_text(encoding="utf-8"),
        (KNOWLEDGE_DIR / "IDENTITY.md").read_text(encoding="utf-8"),
        (KNOWLEDGE_DIR / "USER.md").read_text(encoding="utf-8"),
    )


def _data_oggi():
    return datetime.now(FUSO_ROMA).date().isoformat()


def raccogli_stato():
    """Le sei fonti di argo/stato.py più la data odierna, in un unico dict
    serializzabile. "oggi" evita al modello di dover calcolare/dedurre la
    data — unico dei due errori del primo collaudo (11/9/2026) causato da un
    dato davvero mancante, non da un'invenzione pura."""
    return {
        "oggi": _data_oggi(),
        "approvazioni_in_attesa": stato.approvazioni_in_attesa(),
        "job_falliti": stato.job_falliti(),
        "escalation_aperte": stato.escalation_aperte(),
        "osservazioni_nuove": stato.osservazioni_nuove(),
        "cantieri_aperti": stato.cantieri_aperti(),
        "attivita_git": stato.attivita_git(),
    }


def _tronca(testo, limite, fonte="STATO.md"):
    """Tronca `testo` a `limite` caratteri con una nota esplicita di
    troncamento (mai un taglio silenzioso) — condivisa da
    _stato_per_prompt (decisioni_aperte_bloccano di orienta/instrada) e dal
    modo brief (sessioni/documento di knowledge del cantiere)."""
    if not testo or len(testo) <= limite:
        return testo
    totale = len(testo)
    return testo[:limite] + f"\n[TRONCATO — {totale} caratteri totali, testo completo in {fonte}]"


def _stato_per_prompt(stato_dict):
    """Copia di stato_dict con decisioni_aperte_bloccano troncato oltre
    LIMITE_DECISIONI_APERTE_CARATTERI, nota di troncamento inclusa. Lavora
    su una copia: non modifica mai l'originale, così chi altro consuma lo
    stesso dict (es. scripts/argo/stato_cli.py per un operatore umano) vede
    sempre il testo intero."""
    copia = copy.deepcopy(stato_dict)
    cantieri = copia.get("cantieri_aperti") or {}
    testo = cantieri.get("decisioni_aperte_bloccano")
    if testo:
        cantieri["decisioni_aperte_bloccano"] = _tronca(testo, LIMITE_DECISIONI_APERTE_CARATTERI)
    return copia


def costruisci_system_prompt(stato_dict, istruzioni):
    """`istruzioni` è il blocco specifico del modo (ISTRUZIONI_ORIENTA,
    ISTRUZIONI_INSTRADA o ISTRUZIONI_AVVISA): SOUL/IDENTITY/USER e la
    serializzazione dello stato sono identiche per ogni modo, solo le
    regole comportamentali e la forma di `stato_dict` cambiano — orienta e
    instrada passano le sei fonti di raccogli_stato(), avvisa passa solo i
    candidati già filtrati (vedi _filtra_candidati_avviso)."""
    soul, identity, user = _leggi_identita()
    stato_serializzato = json.dumps(
        _stato_per_prompt(stato_dict), default=str, ensure_ascii=False, separators=(",", ":")
    )
    return (
        f"{soul}\n\n{identity}\n\n{user}\n\n"
        f"{istruzioni}\n\n"
        f"## Dati per questa risposta (formato JSON compatto)\n\n"
        f"{stato_serializzato}"
    )


def genera_risposta():
    """Modo "orienta": raccoglie lo stato, costruisce il prompt, chiama l'LLM.
    Ritorna il testo da mandare a Leonardo."""
    stato_dict = raccogli_stato()
    system = costruisci_system_prompt(stato_dict, ISTRUZIONI_ORIENTA)
    return chiama(system, DOMANDA_LEONARDO, max_tokens=MAX_TOKENS_RISPOSTA, temperature=0.0)


def genera_risposta_instrada(minuti, contesto):
    """Modo "instrada": stessa raccolta di stato di genera_risposta(), istruzioni e
    domanda diverse. `minuti` intero positivo, `contesto` in {"telefono","computer"}
    — già validati da connectors.telegram.interpreta_instrada prima di arrivare qui."""
    stato_dict = raccogli_stato()
    system = costruisci_system_prompt(stato_dict, ISTRUZIONI_INSTRADA)
    domanda = _domanda_instrada(minuti, contesto)
    return chiama(system, domanda, max_tokens=MAX_TOKENS_RISPOSTA, temperature=0.0)


def _filtra_candidati_avviso(righe_approvazioni, righe_job_falliti, righe_osservazioni, chiavi_gia_avvisate):
    """Pura: nessun accesso DB, nessuna chiamata LLM. Applica le tre soglie
    del brief e l'anti-ripetizione one-shot (chiavi_gia_avvisate, da
    alert_inviati con prefisso avvisa_*/osservazioni già 'nuova' — chi
    chiama passa solo osservazioni non ancora riferite). Ritorna
    (candidati, marcatori): candidati è None se NIENTE qualifica — è questo
    il punto in cui si decide il silenzio, prima di ogni chiamata LLM.
    Taglia a LIMITE_VOCI_AVVISO per categoria; l'eccedenza resta non
    marcata e riemerge alla prossima esecuzione, non è persa."""
    approvazioni_ok, chiavi_appr = [], []
    for riga in righe_approvazioni:
        if (riga.get("ore_ferma") or 0) <= SOGLIA_APPROVAZIONE_ORE:
            continue
        chiave = f"{PREFISSO_ALERT_APPROVAZIONE}:{riga['id']}"
        if chiave in chiavi_gia_avvisate:
            continue
        approvazioni_ok.append(riga)
        chiavi_appr.append(chiave)
    approvazioni_ok = approvazioni_ok[:LIMITE_VOCI_AVVISO]
    chiavi_appr = chiavi_appr[:LIMITE_VOCI_AVVISO]

    job_ok, chiavi_job = [], []
    for riga in righe_job_falliti:
        firma = hashlib.sha256(
            f"{riga.get('tipo')}|{riga.get('ultimo_errore')}".encode("utf-8")
        ).hexdigest()[:12]
        chiave = f"{PREFISSO_ALERT_JOB}:{riga.get('tipo')}:{firma}"
        if chiave in chiavi_gia_avvisate:
            continue
        job_ok.append(riga)
        chiavi_job.append(chiave)
    job_ok = job_ok[:LIMITE_VOCI_AVVISO]
    chiavi_job = chiavi_job[:LIMITE_VOCI_AVVISO]

    osservazioni_ok = [
        r for r in righe_osservazioni
        if (r.get("severita") or "").strip().lower() == SEVERITA_GRAVE
    ][:LIMITE_VOCI_AVVISO]

    if not approvazioni_ok and not job_ok and not osservazioni_ok:
        return None, {}

    candidati = {
        "oggi": _data_oggi(),
        "approvazioni_da_segnalare": approvazioni_ok,
        "job_falliti_da_segnalare": job_ok,
        "osservazioni_da_segnalare": osservazioni_ok,
    }
    marcatori = {
        "alert_chiavi": chiavi_appr + chiavi_job,
        "osservazioni_id": [r["id"] for r in osservazioni_ok],
    }
    return candidati, marcatori


def _raccogli_dati_avviso():
    """Impura: le tre letture di stato + le due su alert_inviati, poi
    _filtra_candidati_avviso. Solleva RuntimeError se una fonte ha
    copertura "assente" (lettura DB fallita davvero) invece di trattarla
    come "niente da dire" — altrimenti un guasto di lettura sembrerebbe una
    sera tranquilla, il contrario della fedeltà di SOUL.md."""
    approvazioni = stato.approvazioni_in_attesa()
    job_falliti = stato.job_falliti_recenti(FINESTRA_JOB_FALLITI_ORE)
    osservazioni = stato.osservazioni_nuove()
    chiavi_appr = stato.chiavi_alert_con_prefisso(PREFISSO_ALERT_APPROVAZIONE)
    chiavi_job = stato.chiavi_alert_con_prefisso(PREFISSO_ALERT_JOB)

    for fonte, nome in (
        (approvazioni, "approvazioni_in_attesa"),
        (job_falliti, "job_falliti_recenti"),
        (osservazioni, "osservazioni_nuove"),
        (chiavi_appr, "chiavi_alert_con_prefisso (approvazioni)"),
        (chiavi_job, "chiavi_alert_con_prefisso (job)"),
    ):
        if fonte["copertura"] == "assente":
            raise RuntimeError(f"avviso: lettura di stato fallita per {nome}: {fonte['motivo']}")

    chiavi_gia_avvisate = chiavi_appr["chiavi"] | chiavi_job["chiavi"]
    return _filtra_candidati_avviso(
        approvazioni["righe"], job_falliti["righe"], osservazioni["righe"], chiavi_gia_avvisate
    )


def genera_avviso():
    """Modo "avvisa": digest serale. Se non c'è nessun candidato, ritorna
    (None, {}) SENZA MAI chiamare l'LLM — il silenzio è deciso in Python,
    non lasciato al giudizio del modello. Altrimenti ritorna (testo,
    marcatori): marcatori va scritto da chi chiama DOPO un invio riuscito
    (questo modulo resta sola lettura, vedi guardrail statico nei test)."""
    candidati, marcatori = _raccogli_dati_avviso()
    if candidati is None:
        return None, {}
    system = costruisci_system_prompt(candidati, ISTRUZIONI_AVVISA)
    testo = chiama(system, DOMANDA_AVVISA, max_tokens=MAX_TOKENS_RISPOSTA, temperature=0.0)
    return testo, marcatori


class BriefErrore(Exception):
    """Errore rumoroso: JSON non valido o chiavi mancanti nella risposta
    del modo brief. Motivo sempre categorico, mai il testo grezzo del
    modello (stesso stile di brain/classifier.py:ClassificazioneErrore)."""


def _risolvi_cantiere(nome_utente, cantieri):
    """Match tollerante per sottostringa, case-insensitive, sul testo
    digitato da Leonardo dopo /brief. Mai un match "intelligente" o fuzzy:
    o il testo digitato compare dentro il nome del cantiere, o no — decidere
    cosa fare con zero o più di un risultato spetta a chi chiama
    (genera_brief), non a questa funzione."""
    chiave = (nome_utente or "").strip().lower()
    if not chiave:
        return []
    return [c for c in cantieri if chiave in c["nome"].lower()]


def _documento_cantiere(nome_cantiere):
    """Documento di knowledge associato al cantiere risolto, se una parola
    di DOCUMENTI_CANTIERE compare nel suo nome normalizzato e il file
    esiste davvero. Ritorna (None, None) altrimenti — "se esiste", non
    un errore se manca."""
    chiave = stato.chiave_cantiere(nome_cantiere)
    for parola, path in DOCUMENTI_CANTIERE.items():
        if parola in chiave and path.exists():
            testo = _tronca(
                path.read_text(encoding="utf-8"),
                LIMITE_DOCUMENTO_CANTIERE_CARATTERI,
                fonte=path.name,
            )
            return path.name, testo
    return None, None


def _testo_campo_brief(valore):
    """Il modello a volte restituisce un campo del brief come lista JSON
    (una voce per riga) invece che come stringa unica, nonostante il prompt
    chieda esplicitamente una stringa — capita soprattutto su "contesto"
    (un elenco puntato). Normalizza entrambe le forme in una stringa unica
    con "\\n" tra le righe, così _componi_brief non interpola mai un repr
    Python (["- riga1", "- riga2"]) nel testo finale."""
    if isinstance(valore, list):
        return "\n".join(str(riga) for riga in valore).strip()
    return valore


def _componi_brief(cantiere, grezzo, avvertimento_impatti=None):
    """Pura (nessuna chiamata LLM/DB): valida il JSON forzato del modello e
    compone il testo finale, skeleton fisso incluso. Separata da
    genera_brief per restare testabile senza rete — stesso principio delle
    altre funzioni pure di questo file (_filtra_candidati_avviso,
    _domanda_instrada, ...). `avvertimento_impatti` (passo 3 del ponte), se
    valorizzato, va in coda ai Vincoli standard — composto in Python da
    _verifica_impatti_brief, mai affidato al modello che potrebbe
    parafrasarlo o ometterlo."""
    try:
        risultato = json.loads(estrai_json(grezzo))
    except Exception:
        raise BriefErrore("JSON non valido") from None

    contesto = _testo_campo_brief(risultato.get("contesto"))
    obiettivo = _testo_campo_brief(risultato.get("obiettivo"))
    criterio = _testo_campo_brief(risultato.get("criterio_di_chiusura"))
    if not contesto or not obiettivo or not criterio:
        raise BriefErrore("chiavi mancanti o vuote nel JSON del brief")

    vincoli = VINCOLI_STANDARD_BRIEF
    if avvertimento_impatti:
        vincoli = f"{vincoli}\n\n{avvertimento_impatti}"

    return (
        f"{cantiere['nome']}\n\n"
        f"Plan mode obbligatorio.\n\n"
        f"## Contesto\n\n{contesto}\n\n{RIGA_REPO_HA_RAGIONE}\n\n"
        f"## Obiettivo\n\n{obiettivo}\n\n"
        f"## Vincoli\n\n{vincoli}\n\n"
        f"## Criterio di chiusura\n\n{criterio}"
    )


def _estrai_contesto_brief(grezzo):
    """Estrae solo il campo 'contesto' dalla risposta grezza del modello,
    per la verifica impatti (passo 3) — stessa tolleranza di _componi_brief
    su fence markdown/lista invece di stringa. Ritorna None se il JSON non è
    valido: non solleva mai BriefErrore, quella responsabilità resta di
    _componi_brief, chiamata comunque subito dopo nel flusso di
    genera_brief."""
    try:
        risultato = json.loads(estrai_json(grezzo))
    except Exception:
        return None
    return _testo_campo_brief(risultato.get("contesto"))


def _file_citati_in_contesto(contesto):
    """Candidati file dal testo 'contesto' del brief: solo token con
    un'estensione puntata che esistono davvero sul filesystem del repo —
    stesso controllo deterministico di _risolvi_flag_impatti, non
    un'euristica sul nome. Un percorso indovinato male dal modello (es.
    'pavimento.mjs' nudo mentre il file vero sta in una cartella) non passa
    il controllo: nessun avviso, nessun errore, limite noto non rincorso
    (vedi il brief della sessione). Cap a LIMITE_FILE_IMPATTI_BRIEF, ordine
    di comparsa, senza duplicati."""
    trovati = []
    for m in _FILE_CON_ESTENSIONE_RE.finditer(contesto or ""):
        candidato = m.group(0).strip(".,;:()[]")
        if candidato in trovati:
            continue
        if (REPO_ROOT / candidato).is_file():
            trovati.append(candidato)
        if len(trovati) >= LIMITE_FILE_IMPATTI_BRIEF:
            break
    return trovati


def _contratti_in_gioco(righe):
    """ID dei contratti elencati sotto 'CONTRATTI IN GIOCO' nell'output di
    impatti.py (formato fisso: '  {id}  {enunciato}', poi una riga
    '        garantito_da: ...' con indentazione maggiore che questa regex
    non cattura). Ferma alla prima riga vuota o a 'nessuno'. `righe` è
    l'output già splittato per riga (stdout.splitlines())."""
    try:
        i = righe.index("CONTRATTI IN GIOCO")
    except ValueError:
        return []
    ids = []
    for riga in righe[i + 1:]:
        if not riga.strip() or riga.strip() == "nessuno":
            break
        m = re.match(r"^  (\S+)  ", riga)
        if m:
            ids.append(m.group(1))
    return ids


def _analizza_output_impatti_file(stdout):
    """Deterministico, no LLM: legge l'output di 'impatti.py --file' (formato
    fisso, mai modificato) e ritorna (condivisi, contratti) — condivisi sono
    i nomi sulle righe '  → nome' che menzionano la parola 'condiviso' (sia
    la scheda condivisa stessa sia una pipeline raggiunta 'via componente
    condiviso'; una pipeline dedicata senza condivisi non la contiene mai).
    Il caso 'non è mappato da nessuna scheda' va gestito PRIMA di chiamare
    questa funzione (nessuna riga '→' da leggere in quel caso)."""
    righe = stdout.splitlines()
    condivisi = []
    for riga in righe:
        m = re.match(r"^\s*→\s+(\S+)", riga)
        if m and "condiviso" in riga:
            condivisi.append(m.group(1))
    return condivisi, _contratti_in_gioco(righe)


def _verifica_impatti_brief(contesto):
    """Modo brief, passo 3: interroga impatti.py sui file citati in
    `contesto` (fino a LIMITE_FILE_IMPATTI_BRIEF). Deterministico, mai
    affidato all'LLM: il parsing dell'output di impatti.py è su un formato
    fisso, non un giudizio. Ritorna (avvertimento, log):
    - avvertimento: blocco testo per i Vincoli del brief, None se nessun
      file citato tocca componenti condivisi o contratti — il silenzio è
      l'esito normale, zero righe vuote (come per il modo avvisa).
    - log: traccia della consultazione per il mandato, None solo se nessun
      file citato esiste davvero nel repo (nessuna consultazione avvenuta).
    Un fallimento di impatti.py su un singolo file (returncode!=0, timeout,
    eccezione) non blocca mai il brief: quel file viene solo annotato nel
    log e ignorato ai fini dell'avvertimento."""
    file_validi = _file_citati_in_contesto(contesto)
    if not file_validi:
        return None, None

    righe_avviso = []
    righe_log = []
    for f in file_validi:
        try:
            returncode, stdout, _stderr = _esegui_impatti("--file", f)
        except Exception as e:
            righe_log.append(f"{f}: consultazione fallita ({type(e).__name__})")
            continue
        if returncode != 0:
            righe_log.append(f"{f}: impatti.py fallito (returncode {returncode}), ignorato")
            continue
        if "non è mappato da nessuna scheda" in stdout:
            righe_log.append(f"{f}: non mappato dalla mappa")
            continue

        condivisi, contratti = _analizza_output_impatti_file(stdout)
        if condivisi or contratti:
            parti = []
            if condivisi:
                parti.append("condivisi/pipeline: " + ", ".join(sorted(set(condivisi))))
            if contratti:
                parti.append("contratti: " + ", ".join(contratti))
            dettaglio = "; ".join(parti)
            righe_avviso.append(f"- {f}: {dettaglio}")
            righe_log.append(f"{f}: {dettaglio}")
        else:
            righe_log.append(f"{f}: nessun componente condiviso o contratto")

    avvertimento = None
    if righe_avviso:
        avvertimento = (
            "Avvertimento impatti — questi file toccano componenti condivisi o contratti:\n"
            + "\n".join(righe_avviso)
            + "\nLancia scripts/panoptes/impatti.py sui file sopra prima di modificarli."
        )
    return avvertimento, "; ".join(righe_log)


def genera_brief(nome_utente):
    """Modo "brief": risolve `nome_utente` contro il blocco '## CANTIERI' di
    STATO.md (match tollerante per sottostringa, vedi _risolvi_cantiere —
    MAI indovina: ambiguo o non trovato ritorna l'elenco dei nomi validi,
    zero chiamate LLM su questo percorso), raccoglie il contesto del
    cantiere risolto (riga CANTIERI, ultime N_SESSIONI_BRIEF sessioni,
    documento di knowledge se mappato) e fa scrivere all'LLM
    Contesto/Obiettivo/Criterio di chiusura in JSON forzato (vedi
    _componi_brief per la validazione e la composizione finale). Ritorna
    (testo, log_consultazione_impatti): il secondo elemento (passo 3 del
    ponte) è None ogni volta che non è avvenuta nessuna consultazione di
    impatti.py — compreso ogni ramo che ritorna prima di chiamare l'LLM —
    e va scritto su un mandato da chi chiama (questo modulo resta sola
    lettura, vedi guardrail statico nei test)."""
    stato_cantieri = stato.cantieri_aperti()
    if stato_cantieri["copertura"] != "completa":
        raise RuntimeError(
            f"brief: blocco '## CANTIERI' non affidabile: {stato_cantieri['motivo']}"
        )
    cantieri = stato_cantieri["cantieri"]

    trovati = _risolvi_cantiere(nome_utente, cantieri)
    nomi_validi = "\n".join(f"- {c['nome']}" for c in cantieri)
    if not trovati:
        return f'Nessun cantiere corrisponde a "{nome_utente}". Cantieri validi:\n{nomi_validi}', None
    if len(trovati) > 1:
        nomi_ambigui = ", ".join(c["nome"] for c in trovati)
        return (
            f'"{nome_utente}" è ambiguo, corrisponde a più di un cantiere '
            f"({nomi_ambigui}). Cantieri validi:\n{nomi_validi}"
        ), None

    cantiere = trovati[0]
    sessioni = stato.sessioni_cantiere(cantiere["nome"], n=N_SESSIONI_BRIEF)
    nome_doc, testo_doc = _documento_cantiere(cantiere["nome"])

    dati = {
        "oggi": _data_oggi(),
        "cantiere": cantiere,
        "sessioni_recenti": [
            {
                "titolo": s["titolo"],
                "testo": _tronca(s["testo"], LIMITE_SESSIONI_CANTIERE_CARATTERI),
            }
            for s in sessioni["sezioni"]
        ],
        "documento_knowledge": {"file": nome_doc, "testo": testo_doc} if nome_doc else None,
    }

    system = costruisci_system_prompt(dati, ISTRUZIONI_BRIEF)
    try:
        grezzo = chiama(system, DOMANDA_BRIEF, max_tokens=MAX_TOKENS_BRIEF, temperature=0.0)
    except TettoLLMRaggiunto:
        raise
    except LLMErrore as e:
        raise BriefErrore("chiamata LLM fallita") from e

    avvertimento, log_consultazione = None, None
    contesto = _estrai_contesto_brief(grezzo)
    if contesto:
        avvertimento, log_consultazione = _verifica_impatti_brief(contesto)

    testo = _componi_brief(cantiere, grezzo, avvertimento_impatti=avvertimento)
    return testo, log_consultazione


class ImpattoErrore(Exception):
    """Errore rumoroso: la chiamata LLM del modo impatto è fallita (stesso
    stile di BriefErrore/ClassificazioneErrore). Non usata per l'errore vero
    di impatti.py (percorso o componente inesistente): quel caso non chiama
    mai l'LLM, vedi genera_impatto."""


def _risolvi_flag_impatti(componente_o_file):
    """--file se la parte prima di un eventuale ':riga'/':start-end' esiste
    davvero sul filesystem del repo, altrimenti --componente. Deterministico
    (un controllo su disco, non un'euristica sul nome): un percorso di file
    reale vince sempre su un nome che assomigli a un componente, e viceversa
    — mai indovinato, coerente con _risolvi_cantiere/interpreta_instrada."""
    parte_percorso = componente_o_file.split(":", 1)[0]
    if (REPO_ROOT / parte_percorso).exists():
        return "--file"
    return "--componente"


def _esegui_impatti(flag, valore):
    """Lancia scripts/panoptes/impatti.py in sottoprocesso, mai modificato
    (vincolo del passo 2 del ponte): invocato com'è, nella sua unica
    modalità reale (testo su stdout/stderr, niente --json — non esiste).
    Ritorna (returncode, stdout, stderr)."""
    risultato = subprocess.run(
        ["python3", str(IMPATTI_SCRIPT), flag, valore],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=30,
    )
    return risultato.returncode, risultato.stdout, risultato.stderr


def genera_impatto(componente_o_file):
    """Modo "impatto": scripts/panoptes/impatti.py sul componente o file
    indicato, poi (solo se lo script è riuscito) la traduzione dell'LLM in
    poche righe. Ritorna (testo, esito): esito va scritto sul mandato da chi
    chiama (scripts/argo/orienta_webhook.py, che scrive — questo modulo resta
    sola lettura). Sull'errore vero di impatti.py (returncode != 0: percorso
    o componente/tabella inesistente, mappa non parsabile) NESSUNA chiamata
    LLM: il messaggio di impatti.py è già deterministico e va rilanciato
    com'è, non interpretato — stesso principio "non indovina" di
    _risolvi_cantiere. Non distingue invece "nessuna scheda impattata" (uno
    dei possibili esiti a returncode 0) da "impatto trovato": entrambi
    passano dall'LLM sotto anti-invenzione stretta, per non dover
    reimplementare dall'esterno, a suon di string-matching sul testo, la
    logica di uno script che questo passo non può modificare."""
    flag = _risolvi_flag_impatti(componente_o_file)
    returncode, stdout, stderr = _esegui_impatti(flag, componente_o_file)

    if returncode != 0:
        messaggio = (stderr or stdout).strip() or "impatti.py non ha prodotto nessun messaggio di errore"
        esito = "fallito: " + _tronca(messaggio, LIMITE_ERRORE_IMPATTI_CARATTERI, fonte="impatti.py").splitlines()[0]
        return messaggio, esito

    dati = {
        "oggi": _data_oggi(),
        "richiesta": componente_o_file,
        "output_impatti": _tronca(stdout.strip(), LIMITE_OUTPUT_IMPATTI_CARATTERI, fonte="impatti.py"),
    }
    system = costruisci_system_prompt(dati, ISTRUZIONI_IMPATTO)
    try:
        testo = chiama(
            system, DOMANDA_IMPATTO, max_tokens=MAX_TOKENS_IMPATTO, temperature=0.0,
            marcatore_se_troncato=MARCATORE_TRONCAMENTO_IMPATTO,
        )
    except TettoLLMRaggiunto:
        raise
    except LLMErrore as e:
        raise ImpattoErrore("chiamata LLM fallita") from e

    return testo, "riuscito"
