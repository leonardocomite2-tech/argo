"""Argo — la voce: i tre modi (orienta, instrada, avvisa) più il modo
"brief" del cantiere Argo — il ponte.

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
in Python, mai chiesto al modello.

Sola lettura: questo modulo non scrive mai sul DB (vedi guardrail statico in
tests/test_argo_voce.py, come già per argo/stato.py). genera_avviso()
ritorna anche `marcatori` — cosa andrebbe scritto DOPO un invio riuscito —
ma non lo scrive: tocca a chi chiama (scripts/argo/orienta_webhook.py, che
gira da host e può scrivere). Zero mandati: passo futuro del cantiere.
"""

import copy
import hashlib
import json
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


def _componi_brief(cantiere, grezzo):
    """Pura (nessuna chiamata LLM/DB): valida il JSON forzato del modello e
    compone il testo finale, skeleton fisso incluso. Separata da
    genera_brief per restare testabile senza rete — stesso principio delle
    altre funzioni pure di questo file (_filtra_candidati_avviso,
    _domanda_instrada, ...)."""
    try:
        risultato = json.loads(estrai_json(grezzo))
    except Exception:
        raise BriefErrore("JSON non valido") from None

    contesto = _testo_campo_brief(risultato.get("contesto"))
    obiettivo = _testo_campo_brief(risultato.get("obiettivo"))
    criterio = _testo_campo_brief(risultato.get("criterio_di_chiusura"))
    if not contesto or not obiettivo or not criterio:
        raise BriefErrore("chiavi mancanti o vuote nel JSON del brief")

    return (
        f"{cantiere['nome']}\n\n"
        f"Plan mode obbligatorio.\n\n"
        f"## Contesto\n\n{contesto}\n\n{RIGA_REPO_HA_RAGIONE}\n\n"
        f"## Obiettivo\n\n{obiettivo}\n\n"
        f"## Vincoli\n\n{VINCOLI_STANDARD_BRIEF}\n\n"
        f"## Criterio di chiusura\n\n{criterio}"
    )


def genera_brief(nome_utente):
    """Modo "brief": risolve `nome_utente` contro il blocco '## CANTIERI' di
    STATO.md (match tollerante per sottostringa, vedi _risolvi_cantiere —
    MAI indovina: ambiguo o non trovato ritorna l'elenco dei nomi validi,
    zero chiamate LLM su questo percorso), raccoglie il contesto del
    cantiere risolto (riga CANTIERI, ultime N_SESSIONI_BRIEF sessioni,
    documento di knowledge se mappato) e fa scrivere all'LLM
    Contesto/Obiettivo/Criterio di chiusura in JSON forzato (vedi
    _componi_brief per la validazione e la composizione finale)."""
    stato_cantieri = stato.cantieri_aperti()
    if stato_cantieri["copertura"] != "completa":
        raise RuntimeError(
            f"brief: blocco '## CANTIERI' non affidabile: {stato_cantieri['motivo']}"
        )
    cantieri = stato_cantieri["cantieri"]

    trovati = _risolvi_cantiere(nome_utente, cantieri)
    nomi_validi = "\n".join(f"- {c['nome']}" for c in cantieri)
    if not trovati:
        return f'Nessun cantiere corrisponde a "{nome_utente}". Cantieri validi:\n{nomi_validi}'
    if len(trovati) > 1:
        nomi_ambigui = ", ".join(c["nome"] for c in trovati)
        return (
            f'"{nome_utente}" è ambiguo, corrisponde a più di un cantiere '
            f"({nomi_ambigui}). Cantieri validi:\n{nomi_validi}"
        )

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

    return _componi_brief(cantiere, grezzo)
