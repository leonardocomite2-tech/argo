"""Test di argo/voce.py, stile CASI (vedi tests/test_argo_stato.py).
Zero chiamate di rete: il collaudo del testo vero generato dall'LLM è a
mano, con scripts/argo/orienta.py (criterio di chiusura della sessione).
Lancio: python3 tests/test_argo_voce.py
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import argo.voce as voce  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


# --- guardrail statico: argo/voce.py non scrive mai sul DB ---
sorgente = (REPO_ROOT / "argo" / "voce.py").read_text(encoding="utf-8")
verbi_scrittura = re.findall(r"\b(INSERT|UPDATE|DELETE)\b", sorgente, re.IGNORECASE)
caso("nessun verbo di scrittura SQL nel sorgente di argo/voce.py", [], verbi_scrittura)

# --- i tre file identità esistono e non sono vuoti ---
for nome_file in ("SOUL.md", "IDENTITY.md", "USER.md"):
    contenuto = (voce.KNOWLEDGE_DIR / nome_file).read_text(encoding="utf-8")
    caso(f"{nome_file} non è vuoto", True, len(contenuto.strip()) > 0)

# --- costruisci_system_prompt: contiene davvero identità + istruzioni + stato ---
STATO_FINTO = {
    "cantieri_aperti": {"copertura": "parziale", "motivo": "MARCATORE_TEST_MOTIVO"},
}
_prompt = voce.costruisci_system_prompt(STATO_FINTO)

soul, identity, user = voce._leggi_identita()
caso("il system prompt contiene SOUL.md per intero", True, soul in _prompt)
caso("il system prompt contiene IDENTITY.md per intero", True, identity in _prompt)
caso("il system prompt contiene USER.md per intero", True, user in _prompt)
caso("il system prompt contiene le istruzioni del modo orienta", True, voce.ISTRUZIONI_ORIENTA in _prompt)
caso("il system prompt contiene lo stato serializzato passato", True, "MARCATORE_TEST_MOTIVO" in _prompt)

# --- le istruzioni esplicite coprono i punti richiesti dal brief ---
for frammento in (
    "Poche righe",
    "Dai del tu",
    "Conclusione prima",
    "UNA SOLA prossima cosa",
    "copertura",
    "silenzio è un esito normale",
    "Niente incoraggiamenti",
):
    caso(
        f"ISTRUZIONI_ORIENTA copre: {frammento!r}",
        True,
        frammento in voce.ISTRUZIONI_ORIENTA,
    )


def main():
    falliti = 0
    for descrizione, atteso, ottenuto in CASI:
        if ottenuto != atteso:
            falliti += 1
            print(f"FALLITO: {descrizione} — atteso {atteso!r}, ottenuto {ottenuto!r}")
    passati = len(CASI) - falliti
    print(f"{passati}/{len(CASI)} casi passati")
    return 0 if falliti == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
