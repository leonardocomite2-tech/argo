"""Test di connectors/telegram.py:normalizza_comando, usata dal webhook
/webhook/argo (backend/main.py) per riconoscere /orienta. Stile CASI (vedi
tests/test_argo_voce.py). Vive fuori da backend/main.py apposta: quel modulo
importa psycopg/fastapi, non installati nell'ambiente host di test (gira solo
in Docker) — connectors/telegram.py no, quindi resta testabile da qui senza
mock. Il resto di _gestisci_messaggio_argo (DB + invio Telegram) è collaudato
a mano.
Lancio: python3 tests/test_webhook_argo.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.telegram import normalizza_comando  # noqa: E402

COMANDO_ORIENTA = "/orienta"  # stesso valore di backend/main.py:COMANDO_ORIENTA

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


caso("comando pulito", COMANDO_ORIENTA, normalizza_comando("/orienta"))
caso("comando con spazi attorno", COMANDO_ORIENTA, normalizza_comando("  /orienta  "))
caso("comando con suffisso @NomeBot (gruppi Telegram)", COMANDO_ORIENTA, normalizza_comando("/orienta@ArgoVoceBot"))
caso("comando con testo extra dopo, ignorato", COMANDO_ORIENTA, normalizza_comando("/orienta ora"))
caso("testo vuoto -> None", None, normalizza_comando(""))
caso("solo spazi -> None", None, normalizza_comando("   "))
caso("None -> None", None, normalizza_comando(None))
caso("altro comando resta se stesso, non COMANDO_ORIENTA", "/stato", normalizza_comando("/stato"))
caso("testo libero non è un comando riconosciuto", "ciao,", normalizza_comando("ciao, come va?"))

# --- guardrail statico: backend/main.py usa davvero questo valore per COMANDO_ORIENTA
# (letto come testo, non importato: backend/main.py richiede psycopg/fastapi, non
# installati nell'ambiente host di test) ---
_sorgente_main = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")
caso(
    'backend/main.py: COMANDO_ORIENTA = "/orienta"',
    True,
    f'COMANDO_ORIENTA = "{COMANDO_ORIENTA}"' in _sorgente_main,
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
