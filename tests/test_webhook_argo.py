"""Test di connectors/telegram.py: normalizza_comando/argomenti_comando/
interpreta_instrada, usate dal webhook /webhook/argo (backend/main.py) per
riconoscere /orienta e /instrada. Stile CASI (vedi tests/test_argo_voce.py).
Vivono fuori da backend/main.py apposta: quel modulo importa psycopg/fastapi,
non installati nell'ambiente host di test (gira solo in Docker) —
connectors/telegram.py no, quindi resta testabile da qui senza mock. Il resto
di _gestisci_messaggio_argo (DB + invio Telegram) è collaudato a mano.
Lancio: python3 tests/test_webhook_argo.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.telegram import (  # noqa: E402
    normalizza_comando,
    argomenti_comando,
    interpreta_instrada,
)

COMANDO_ORIENTA = "/orienta"  # stesso valore di backend/main.py:COMANDO_ORIENTA
COMANDO_INSTRADA = "/instrada"  # stesso valore di backend/main.py:COMANDO_INSTRADA
COMANDO_BRIEF = "/brief"  # stesso valore di backend/main.py:COMANDO_BRIEF

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

# --- argomenti_comando: token dopo il comando ---
caso("nessun testo -> []", [], argomenti_comando(""))
caso("solo il comando -> []", [], argomenti_comando("/instrada"))
caso("comando con testo extra -> None -> []", [], argomenti_comando(None))
caso("un argomento", ["20"], argomenti_comando("/instrada 20"))
caso("due argomenti", ["20", "telefono"], argomenti_comando("/instrada 20 telefono"))
caso(
    "due argomenti + testo extra, ignorato più avanti da chi chiama",
    ["20", "telefono", "ora"],
    argomenti_comando("/instrada 20 telefono ora"),
)
caso(
    "argomenti dopo un comando con suffisso @NomeBot",
    ["20", "telefono"],
    argomenti_comando("/instrada@ArgoVoceBot 20 telefono"),
)

# --- argomenti_comando su /brief <nome cantiere>: il nome può avere spazi,
# backend/main.py:_gestisci_messaggio_argo lo ricompone con " ".join(...) ---
caso("brief senza nome -> []", [], argomenti_comando("/brief"))
caso("brief con nome di una parola", ["designer"], argomenti_comando("/brief designer"))
caso(
    "brief con nome multi-parola",
    ["cantiere", "2"],
    argomenti_comando("/brief cantiere 2"),
)
caso(
    "brief con nome multi-parola ricomposto con spazio, come fa backend/main.py",
    "cantiere 2",
    " ".join(argomenti_comando("/brief cantiere 2")),
)

# --- interpreta_instrada: (minuti, contesto, errore) — mai indovina un valore mancante ---
caso("minuti+contesto validi", (20, "telefono", None), interpreta_instrada(["20", "telefono"]))
caso("minuti+contesto validi, computer", (120, "computer", None), interpreta_instrada(["120", "computer"]))
caso(
    "contesto maiuscolo normalizzato",
    (5, "telefono", None),
    interpreta_instrada(["5", "TELEFONO"]),
)
caso("nessun argomento -> chiede i minuti", (None, None, "Quanti minuti hai?"), interpreta_instrada([]))
caso(
    "minuti non numerici -> chiede un numero intero positivo",
    (None, None, "I minuti vanno scritti come numero intero positivo (es. 20)."),
    interpreta_instrada(["venti", "telefono"]),
)
caso(
    "minuti zero -> non valido",
    (None, None, "I minuti vanno scritti come numero intero positivo (es. 20)."),
    interpreta_instrada(["0", "telefono"]),
)
caso(
    "minuti negativi -> non valido (isdigit() rifiuta il segno)",
    (None, None, "I minuti vanno scritti come numero intero positivo (es. 20)."),
    interpreta_instrada(["-5", "telefono"]),
)
caso(
    "contesto mancante -> chiede telefono o computer",
    (20, None, "Sei al telefono o al computer?"),
    interpreta_instrada(["20"]),
)
caso(
    "contesto non riconosciuto -> non indovina",
    (20, None, "Contesto non riconosciuto: telefono o computer?"),
    interpreta_instrada(["20", "metropolitana"]),
)

# --- guardrail statico: backend/main.py usa davvero questi valori per i comandi
# (letto come testo, non importato: backend/main.py richiede psycopg/fastapi, non
# installati nell'ambiente host di test) ---
_sorgente_main = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")
caso(
    'backend/main.py: COMANDO_ORIENTA = "/orienta"',
    True,
    f'COMANDO_ORIENTA = "{COMANDO_ORIENTA}"' in _sorgente_main,
)
caso(
    'backend/main.py: COMANDO_INSTRADA = "/instrada"',
    True,
    f'COMANDO_INSTRADA = "{COMANDO_INSTRADA}"' in _sorgente_main,
)
caso(
    'backend/main.py: COMANDO_BRIEF = "/brief"',
    True,
    f'COMANDO_BRIEF = "{COMANDO_BRIEF}"' in _sorgente_main,
)
caso(
    'backend/main.py: accoda il job "genera_brief" (stringa, tipo di job)',
    True,
    '"genera_brief"' in _sorgente_main,
)
caso(
    "backend/main.py: mai import di argo.voce — la risoluzione/generazione del "
    "brief resta host-only (argo/voce.py non gira in Docker, vedi argo/stato.py)",
    True,
    "import argo" not in _sorgente_main,
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
