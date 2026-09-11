"""Argo — la voce: modo "orienta".

Un solo comportamento: Leonardo è perso, vuole sapere dove. Raccoglie lo
stato con le sei funzioni di sola lettura di `argo/stato.py`, lo passa a un
LLM insieme ai file identità (SOUL/IDENTITY/USER, letti dai file — non
duplicati qui dentro), e ritorna il testo da mandare.

Sola lettura: questo modulo non scrive mai sul DB (vedi guardrail statico in
tests/test_argo_voce.py, come già per argo/stato.py). Zero instrada, zero
avvisa, zero mandati: quelli sono passi futuri del cantiere.
"""

import copy
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
- Niente incoraggiamenti, niente riassunti di ciò che è stato fatto, niente
  percentuali di completamento.
- Le cose ferme sono informazione, non rimprovero.
""".strip()


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


def costruisci_system_prompt(stato_dict):
    soul, identity, user = _leggi_identita()
    stato_serializzato = json.dumps(
        _stato_per_prompt(stato_dict), default=str, ensure_ascii=False, separators=(",", ":")
    )
    return (
        f"{soul}\n\n{identity}\n\n{user}\n\n"
        f"{ISTRUZIONI_ORIENTA}\n\n"
        f"## Stato attuale del sistema (sei fonti + data odierna, formato JSON compatto)\n\n"
        f"{stato_serializzato}"
    )


def genera_risposta():
    """Raccoglie lo stato, costruisce il prompt, chiama l'LLM. Ritorna il
    testo da mandare a Leonardo."""
    stato_dict = raccogli_stato()
    system = costruisci_system_prompt(stato_dict)
    return chiama(system, DOMANDA_LEONARDO, max_tokens=MAX_TOKENS_RISPOSTA, temperature=0.0)
