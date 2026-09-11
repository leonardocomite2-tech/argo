"""Argo — la voce: modo "orienta".

Un solo comportamento: Leonardo è perso, vuole sapere dove. Raccoglie lo
stato con le sei funzioni di sola lettura di `argo/stato.py`, lo passa a un
LLM insieme ai file identità (SOUL/IDENTITY/USER, letti dai file — non
duplicati qui dentro), e ritorna il testo da mandare.

Sola lettura: questo modulo non scrive mai sul DB (vedi guardrail statico in
tests/test_argo_voce.py, come già per argo/stato.py). Zero instrada, zero
avvisa, zero mandati: quelli sono passi futuri del cantiere.
"""

import json
from pathlib import Path

import argo.stato as stato
from connectors.llm import chiama

REPO_ROOT = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = REPO_ROOT / "knowledge" / "argo"

MAX_TOKENS_RISPOSTA = 400
DOMANDA_LEONARDO = "sono perso, dove sono?"

ISTRUZIONI_ORIENTA = """
## Modo "orienta" — istruzioni per questa risposta

Leonardo ti ha appena chiesto: "sono perso, dove sono?". Rispondi seguendo
queste regole, senza eccezioni:

- Poche righe. Mai un elenco di tutto quello che è aperto: se elenchi tutto,
  hai fallito.
- Dai del tu.
- Conclusione prima, contesto dopo.
- Di' UNA SOLA prossima cosa, con il motivo per cui è quella e non un'altra —
  non una lista di opzioni.
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


def raccogli_stato():
    """Le sei fonti di argo/stato.py, in un unico dict serializzabile."""
    return {
        "approvazioni_in_attesa": stato.approvazioni_in_attesa(),
        "job_falliti": stato.job_falliti(),
        "escalation_aperte": stato.escalation_aperte(),
        "osservazioni_nuove": stato.osservazioni_nuove(),
        "cantieri_aperti": stato.cantieri_aperti(),
        "attivita_git": stato.attivita_git(),
    }


def costruisci_system_prompt(stato_dict):
    soul, identity, user = _leggi_identita()
    stato_serializzato = json.dumps(stato_dict, indent=2, default=str, ensure_ascii=False)
    return (
        f"{soul}\n\n{identity}\n\n{user}\n\n"
        f"{ISTRUZIONI_ORIENTA}\n\n"
        f"## Stato attuale del sistema (sei fonti, formato JSON)\n\n"
        f"{stato_serializzato}"
    )


def genera_risposta():
    """Raccoglie lo stato, costruisce il prompt, chiama l'LLM. Ritorna il
    testo da mandare a Leonardo."""
    stato_dict = raccogli_stato()
    system = costruisci_system_prompt(stato_dict)
    return chiama(system, DOMANDA_LEONARDO, max_tokens=MAX_TOKENS_RISPOSTA, temperature=0.0)
