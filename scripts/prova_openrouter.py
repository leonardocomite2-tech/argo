#!/usr/bin/env python3
"""Prova minima del ramo gratuito del gateway LLM.

    python3 scripts/prova_openrouter.py <modello:free>

Una sola chiamata con sensibile=False e fallback=False (niente ripiego
silenzioso su Anthropic): stampa l'esito e la quota gratuita del giorno.
Consuma UNA chiamata della quota gratuita anche se fallisce. Il modello è
obbligatorio: il listino gratuito ruota. Per sceglierne uno compatibile col
vincolo di data policy, gli endpoint ZDR gratuiti sono elencati da
https://openrouter.ai/api/v1/endpoints/zdr (quelli con ":free" nel model_id).
Prompt fisso e senza dati di terzi.
"""
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.llm import carica_env, chiama  # noqa: E402

PROMPT = "Rispondi solo con la parola: funziona"


def main(argv):
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    modello = argv[1]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    carica_env()

    from connectors.openrouter import ErroreOpenRouter
    from connectors.psql_host import psql

    try:
        testo = chiama("Sei un test di connessione.", PROMPT, max_tokens=300,
                       sensibile=False, modello=modello, fallback=False)
        print(f"ESITO: ok — risposta: {testo.strip()!r}")
        esito = 0
    except ErroreOpenRouter as e:
        extra = f" (riprova dopo {e.retry_after}s)" if e.retry_after else ""
        print(f"ESITO: fallita — {type(e).__name__}: {e}{extra}")
        esito = 1

    quota = psql(
        "SELECT COALESCE((SELECT chiamate FROM openrouter_chiamate_giorno "
        "WHERE giorno = (now() AT TIME ZONE 'Europe/Rome')::date), 0)"
    )
    print(f"quota gratuita usata oggi: {quota}")
    return esito


if __name__ == "__main__":
    sys.exit(main(sys.argv))
