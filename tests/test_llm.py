"""Test di connectors/llm.py, stile CASI (vedi tests/test_argo_voce.py).
Zero chiamate di rete: solo la funzione pura _applica_marcatore_troncamento.
Lancio: python3 tests/test_llm.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import connectors.llm as llm  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


MARCATORE = "[TRONCATO]"

caso(
    "_applica_marcatore_troncamento: stop_reason max_tokens + marcatore -> accodato",
    "testo parziale\n[TRONCATO]",
    llm._applica_marcatore_troncamento("testo parziale", "max_tokens", MARCATORE),
)
caso(
    "_applica_marcatore_troncamento: stop_reason end_turn -> testo invariato",
    "testo completo",
    llm._applica_marcatore_troncamento("testo completo", "end_turn", MARCATORE),
)
caso(
    "_applica_marcatore_troncamento: marcatore None (default di chiama()) -> invariato anche con max_tokens",
    "testo parziale",
    llm._applica_marcatore_troncamento("testo parziale", "max_tokens", None),
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
