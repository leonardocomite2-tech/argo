import logging
import os
import time

import psycopg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("argo.worker")

HANDLERS = {}


def handler(tipo):
    def deco(fn):
        HANDLERS[tipo] = fn
        return fn
    return deco


def db_connect():
    return psycopg.connect(
        host="db",
        dbname="argo",
        user="argo",
        password=os.environ["PG_PASSWORD"],
    )


def claim_job():
    """Reclama un job pending: SELECT ... FOR UPDATE SKIP LOCKED + transizione a running,
    nella stessa transazione (commit implicito all'uscita del `with conn`)."""
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, tipo, payload FROM jobs
                WHERE stato = 'pending' AND run_after <= now()
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                LIMIT 1
                """
            )
            row = cur.fetchone()
            if row is None:
                return None
            job_id, tipo, payload = row
            cur.execute(
                """
                UPDATE jobs SET stato = 'running', tentativi = tentativi + 1
                WHERE id = %s
                RETURNING tentativi
                """,
                (job_id,),
            )
            tentativi = cur.fetchone()[0]
    return job_id, tipo, payload, tentativi


def complete_job(job_id):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE jobs SET stato = 'done' WHERE id = %s", (job_id,))


def retry_job(job_id, errore):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE jobs
                SET stato = 'pending', ultimo_errore = %s, run_after = now() + interval '60 seconds'
                WHERE id = %s
                """,
                (errore, job_id),
            )


def fail_job(job_id, errore):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET stato = 'failed', ultimo_errore = %s WHERE id = %s",
                (errore, job_id),
            )


def process_next_job():
    job = claim_job()
    if job is None:
        return
    job_id, tipo, payload, tentativi = job

    fn = HANDLERS.get(tipo)
    if fn is None:
        logger.error("job %s: handler sconosciuto per tipo '%s'", job_id, tipo)
        fail_job(job_id, f"handler sconosciuto per tipo '{tipo}'")
        return

    try:
        fn(payload)
    except Exception as e:
        logger.exception("job %s (%s) fallito", job_id, tipo)
        if tentativi < 2:
            retry_job(job_id, str(e))
        else:
            fail_job(job_id, str(e))
    else:
        complete_job(job_id)


@handler("genera_poster")
def genera_poster(payload):
    logger.info("genera_poster: event_id=%s", payload.get("event_id"))


def recover_orphaned_jobs():
    # Sicuro perché c'è un solo worker: se stato='running' all'avvio, per forza
    # il processo precedente è morto a metà. Con più worker concorrenti questa
    # assunzione non vale più e servirebbe un timeout (es. updated_at troppo vecchio)
    # invece di un reset incondizionato.
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE jobs SET stato = 'pending' WHERE stato = 'running'")
            n = cur.rowcount
    logger.info("recovery avvio: %d job orfani rimessi in pending", n)


def main():
    logger.info("worker avviato")
    recover_orphaned_jobs()
    while True:
        try:
            process_next_job()
        except Exception:
            logger.exception("errore imprevisto nel loop worker")
        time.sleep(5)


if __name__ == "__main__":
    main()
