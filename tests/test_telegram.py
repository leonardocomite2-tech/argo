"""Test di connectors/telegram.py:_spezza_testo/invia_lungo (cantiere Argo —
il ponte, passo 1: un brief supera spesso i 4096 caratteri di un messaggio
Telegram, gli altri modi di Argo restano sempre entro un messaggio). Stile
CASI (vedi tests/test_argo_voce.py). Zero rete: invia_lungo() è collaudata
sostituendo notifica() con un raccoglitore in-memory.
Lancio: python3 tests/test_telegram.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import connectors.telegram as telegram  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


# --- _spezza_testo: sotto il limite, un solo blocco identico all'originale ---
_testo_corto = "riga uno\n\nriga due"
caso("_spezza_testo: sotto il limite ritorna [testo] invariato", [_testo_corto], telegram._spezza_testo(_testo_corto, 100))

# --- _spezza_testo: spezza su paragrafi (doppio a capo) quando possibile ---
_para_a = "A" * 60
_para_b = "B" * 60
_para_c = "C" * 60
_testo_paragrafi = f"{_para_a}\n\n{_para_b}\n\n{_para_c}"
_blocchi = telegram._spezza_testo(_testo_paragrafi, 130)
caso("_spezza_testo: nessun blocco supera il limite", True, all(len(b) <= 130 for b in _blocchi))
caso(
    "_spezza_testo: concatenando i blocchi si ricostruisce il testo originale",
    _testo_paragrafi,
    "\n\n".join(_blocchi),
)

# --- _spezza_testo: un paragrafo da solo più lungo del limite si spezza su riga ---
_riga_1 = "X" * 40
_riga_2 = "Y" * 40
_riga_3 = "Z" * 40
_paragrafo_lungo = f"{_riga_1}\n{_riga_2}\n{_riga_3}"
_blocchi_riga = telegram._spezza_testo(_paragrafo_lungo, 50)
caso("_spezza_testo: paragrafo lungo spezzato su riga, nessun blocco supera il limite", True, all(len(b) <= 50 for b in _blocchi_riga))
caso(
    "_spezza_testo: concatenando con \\n si ricostruisce il paragrafo originale",
    _paragrafo_lungo,
    "\n".join(_blocchi_riga),
)

# --- _spezza_testo: mai un blocco vuoto ---
caso("_spezza_testo: nessun blocco vuoto tra i paragrafi", True, all(b for b in _blocchi))
caso("_spezza_testo: nessun blocco vuoto nello spezzamento a riga", True, all(b for b in _blocchi_riga))

# --- _spezza_testo: caso limite, una singola riga più lunga del limite (taglio secco) ---
_riga_fiume = "Q" * 120
_blocchi_fiume = telegram._spezza_testo(_riga_fiume, 50)
caso("_spezza_testo: riga senza a-capo tagliata secco, nessun blocco supera il limite", True, all(len(b) <= 50 for b in _blocchi_fiume))
caso("_spezza_testo: taglio secco non perde caratteri", _riga_fiume, "".join(_blocchi_fiume))

# --- invia_lungo: manda un solo messaggio quando il testo sta nel limite
# (comportamento identico a notifica() diretta per orienta/instrada/avvisa) ---
_inviati = []


def _notifica_finta(testo, token=None):
    _inviati.append((testo, token))


_notifica_originale = telegram.notifica
try:
    telegram.notifica = _notifica_finta

    _inviati.clear()
    telegram.invia_lungo("messaggio breve", token="tok123")
    caso("invia_lungo: testo breve -> un solo invio", 1, len(_inviati))
    caso("invia_lungo: testo breve -> invio identico all'originale", ("messaggio breve", "tok123"), _inviati[0])

    _inviati.clear()
    _testo_lungo_brief = "\n\n".join(["Sezione " + str(i) + " " + ("x" * 3000) for i in range(1, 4)])
    telegram.invia_lungo(_testo_lungo_brief, token="tok123")
    caso("invia_lungo: testo lungo -> più di un invio", True, len(_inviati) > 1)
    caso(
        "invia_lungo: nessun blocco supera LIMITE_TELEGRAM",
        True,
        all(len(t) <= telegram.LIMITE_TELEGRAM for t, _ in _inviati),
    )
    caso(
        "invia_lungo: concatenando i blocchi inviati (separati da \\n\\n) si ricostruisce il testo originale",
        _testo_lungo_brief,
        "\n\n".join(t for t, _ in _inviati),
    )
    caso(
        "invia_lungo: nessun marcatore 'parte' iniettato nel testo inviato",
        True,
        all("parte" not in t.lower() for t, _ in _inviati),
    )
    caso("invia_lungo: token passato a ogni invio", True, all(tok == "tok123" for _, tok in _inviati))
finally:
    telegram.notifica = _notifica_originale


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
