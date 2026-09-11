"""Argo — la voce: i tre modi (orienta, instrada, avvisa).

Orienta e instrada rispondono a Leonardo: raccolgono lo stato con le sei
funzioni di sola lettura di `argo/stato.py`, lo passano a un LLM insieme ai
file identità (SOUL/IDENTITY/USER, letti dai file — non duplicati qui
dentro), e ritornano il testo da mandare. Avvisa è l'unico modo in cui è
Argo a scrivere per primo (digest serale) — la selezione di COSA dire è
deterministica in Python (vedi _filtra_candidati_avviso), l'LLM redige solo
il testo di ciò che è già stato deciso di dire.

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
from connectors.llm import chiama

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


def _stato_per_prompt(stato_dict):
    """Copia di stato_dict con decisioni_aperte_bloccano troncato oltre
    LIMITE_DECISIONI_APERTE_CARATTERI, nota di troncamento inclusa. Lavora
    su una copia: non modifica mai l'originale, così chi altro consuma lo
    stesso dict (es. scripts/argo/stato_cli.py per un operatore umano) vede
    sempre il testo intero."""
    copia = copy.deepcopy(stato_dict)
    cantieri = copia.get("cantieri_aperti") or {}
    testo = cantieri.get("decisioni_aperte_bloccano")
    if testo and len(testo) > LIMITE_DECISIONI_APERTE_CARATTERI:
        totale = len(testo)
        cantieri["decisioni_aperte_bloccano"] = (
            testo[:LIMITE_DECISIONI_APERTE_CARATTERI]
            + f"\n[TRONCATO — {totale} caratteri totali, testo completo in STATO.md]"
        )
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
