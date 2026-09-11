#!/usr/bin/env python3
"""python3 scripts/argo/orienta_webhook.py

Consumer host-side del job 'genera_orienta', accodato da backend/main.py
(POST /webhook/argo) quando Leonardo scrive /orienta al bot Argo da
Telegram. Lanciato da cron ogni minuto, non da Docker: argo/voce.py passa
da argo/stato.py, che deve girare da host (docker exec + STATO.md + git sul
filesystem del repo — vedi il docstring di argo/stato.py). worker/loop.py
esclude esplicitamente 'genera_orienta' dal proprio claim_job() per questo
motivo.

Ad ogni lancio reclama al più un job pending, stesso idiom atomico di
worker/loop.py:claim_job (UPDATE ... WHERE stato='pending' RETURNING id),
ma via `docker exec argo-db-1 psql` invece di psycopg diretto — stessa
convenzione di argo/stato.py, dato che gira da host come quel modulo.

Nessun retry automatico su errore (stesso trade-off già scelto per
classificazione/bozza, vedi STATO.md — DECISIONI APERTE): un fallimento è
terminale per quella richiesta, Leonardo la ripete con un altro /orienta.
Mai un fallimento silenzioso: un errore avvisa comunque su Telegram.
"""

import logging
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.llm import carica_env  # noqa: E402

carica_env()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("argo.orienta_webhook")

CONTAINER_DB = "argo-db-1"
TIPO_JOB = "genera_orienta"


def _psql(sql, timeout=15):
    """Esegue `sql` via docker exec (stessa convenzione di argo/stato.py, non
    riusabile qui: quel modulo è dichiaratamente sola-lettura e non scrive
    mai). Ritorna stdout grezzo, stripped."""
    risultato = subprocess.run(
        ["docker", "exec", CONTAINER_DB, "psql", "-U", "argo", "-d", "argo", "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if risultato.returncode != 0:
        raise RuntimeError(f"psql fallito: {risultato.stderr.strip()[:300]}")
    return risultato.stdout.strip()


def _reclama_job():
    """Claim atomico: prima trova il pending più vecchio, poi lo reclama con
    una UPDATE guardata su stato='pending' — se nel frattempo un altro
    lancio di questo stesso script lo ha già preso, la UPDATE non tocca
    righe e questo lancio esce a mani vuote (nessun doppio invio)."""
    riga = _psql(
        f"SELECT id FROM jobs WHERE tipo='{TIPO_JOB}' AND stato='pending' ORDER BY id LIMIT 1"
    )
    if not riga:
        return None
    job_id = int(riga)
    claimato = _psql(
        f"UPDATE jobs SET stato='running', tentativi=tentativi+1 "
        f"WHERE id={job_id} AND stato='pending' RETURNING id"
    )
    return job_id if claimato else None


def _segna_done(job_id):
    _psql(f"UPDATE jobs SET stato='done' WHERE id={job_id}")


def _segna_failed(job_id, errore):
    errore_sql = errore.replace("'", "''")[:500]
    _psql(f"UPDATE jobs SET stato='failed', ultimo_errore='{errore_sql}' WHERE id={job_id}")


def main():
    job_id = _reclama_job()
    if job_id is None:
        return

    from argo.voce import genera_risposta
    from connectors.telegram import notifica

    try:
        testo = genera_risposta()
    except Exception as e:
        logger.exception("orienta_webhook: job %s fallito", job_id)
        _segna_failed(job_id, f"{type(e).__name__}: {e}")
        notifica(
            "Errore nel generare l'orientamento — riprova con /orienta.",
            token=os.environ["ARGO_VOCE_BOT_TOKEN"],
        )
        return

    notifica(testo, token=os.environ["ARGO_VOCE_BOT_TOKEN"])
    _segna_done(job_id)


if __name__ == "__main__":
    main()
