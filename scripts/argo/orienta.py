#!/usr/bin/env python3
"""python3 scripts/argo/orienta.py

Lancia a mano il modo "orienta": genera la risposta con argo/voce.py, la
stampa a terminale e la manda sul bot Telegram nuovo (ARGO_VOCE_BOT_TOKEN,
stesso TELEGRAM_CHAT_ID del bot meccanico). Va lanciato da host, come
scripts/argo/stato_cli.py: argo/stato.py legge STATO.md e git dal filesystem
del repo, e le fonti DB passano da `docker exec argo-db-1 psql`.

Nessuna scrittura sul DB, nessun polling: un comando, una risposta.
"""

import logging
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.llm import carica_env  # noqa: E402

carica_env()  # legge .env se non già in ambiente: ANTHROPIC_API_KEY, LLM_TETTO_GIORNALIERO,
              # ARGO_VOCE_BOT_TOKEN, TELEGRAM_CHAT_ID (carica_env itera tutte le chiavi)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

from argo.voce import genera_risposta  # noqa: E402
from connectors.telegram import notifica  # noqa: E402


def main():
    testo = genera_risposta()
    print(testo)
    notifica(testo, token=os.environ["ARGO_VOCE_BOT_TOKEN"])


if __name__ == "__main__":
    main()
