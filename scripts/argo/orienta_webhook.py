#!/usr/bin/env python3
"""python3 scripts/argo/orienta_webhook.py

Consumer host-side dei job 'genera_orienta' e 'genera_instrada' (passo 6,
generalizzato — nome file invariato apposta: il crontab di Leonardo lancia
già questo script ogni minuto, rinominarlo lo romperebbe in silenzio),
accodati da backend/main.py (POST /webhook/argo) quando Leonardo scrive
/orienta o /instrada al bot Argo da Telegram. Lanciato da cron, non da
Docker: argo/voce.py passa da argo/stato.py, che deve girare da host (docker
exec + STATO.md + git sul filesystem del repo — vedi il docstring di
argo/stato.py). worker/loop.py esclude esplicitamente entrambi i tipi dal
proprio claim_job() per questo motivo.

Ad ogni lancio reclama al più un job pending (il più vecchio dei due tipi,
FIFO), stesso idiom atomico di worker/loop.py:claim_job (UPDATE ...
WHERE stato='pending' RETURNING id), ma via `docker exec argo-db-1 psql`
invece di psycopg diretto — stessa convenzione di argo/stato.py, dato che
gira da host come quel modulo. Selezione multi-colonna (id, tipo, payload)
avvolta in json_agg, stesso stile robusto di argo/stato.py:_query_db.

Nessun retry automatico su errore (stesso trade-off già scelto per
classificazione/bozza, vedi STATO.md — DECISIONI APERTE): un fallimento è
terminale per quella richiesta, Leonardo la ripete con un altro comando.
Mai un fallimento silenzioso: un errore avvisa comunque su Telegram.
"""

import json
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
TIPI_JOB = ("genera_orienta", "genera_instrada")


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
    """Claim atomico: prima trova il pending più vecchio tra i due tipi (FIFO),
    poi lo reclama con una UPDATE guardata su stato='pending' — se nel frattempo
    un altro lancio di questo stesso script lo ha già preso, la UPDATE non tocca
    righe e questo lancio esce a mani vuote (nessun doppio invio). Ritorna
    (job_id, tipo, payload) o None."""
    tipi_sql = ",".join(f"'{t}'" for t in TIPI_JOB)
    riga = _psql(
        "SELECT json_agg(t) FROM (SELECT id, tipo, payload FROM jobs "
        f"WHERE tipo IN ({tipi_sql}) AND stato='pending' ORDER BY id LIMIT 1) t"
    )
    if not riga or riga == "null":
        return None
    job = json.loads(riga)[0]
    job_id = job["id"]
    claimato = _psql(
        f"UPDATE jobs SET stato='running', tentativi=tentativi+1 "
        f"WHERE id={job_id} AND stato='pending' RETURNING id"
    )
    if not claimato:
        return None
    return job_id, job["tipo"], job.get("payload") or {}


def _segna_done(job_id):
    _psql(f"UPDATE jobs SET stato='done' WHERE id={job_id}")


def _segna_failed(job_id, errore):
    errore_sql = errore.replace("'", "''")[:500]
    _psql(f"UPDATE jobs SET stato='failed', ultimo_errore='{errore_sql}' WHERE id={job_id}")


def main():
    reclamato = _reclama_job()
    if reclamato is None:
        return
    job_id, tipo, payload = reclamato

    from argo.voce import genera_risposta, genera_risposta_instrada
    from connectors.telegram import notifica

    comando_ripeti = "/orienta" if tipo == "genera_orienta" else "/instrada"
    try:
        if tipo == "genera_orienta":
            testo = genera_risposta()
        else:
            testo = genera_risposta_instrada(payload["minuti"], payload["contesto"])
    except Exception as e:
        logger.exception("orienta_webhook: job %s (%s) fallito", job_id, tipo)
        _segna_failed(job_id, f"{type(e).__name__}: {e}")
        notifica(
            f"Errore nel generare la risposta — riprova con {comando_ripeti}.",
            token=os.environ["ARGO_VOCE_BOT_TOKEN"],
        )
        return

    notifica(testo, token=os.environ["ARGO_VOCE_BOT_TOKEN"])
    _segna_done(job_id)


if __name__ == "__main__":
    main()
