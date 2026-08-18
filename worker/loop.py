import logging
import os
import time
from pathlib import Path

import psycopg

from media.poster import BASE_DIR, genera_poster as genera_poster_immagine
from connectors.mailer import invia_email
from connectors.testi import OGGETTO_POSTER, CORPO_POSTER

POSTER_AI_PATH = BASE_DIR / "templates" / "poster_ai.png"

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
    event_id = payload.get("event_id")
    if not event_id:
        raise ValueError("genera_poster: event_id mancante nel payload del job")

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT payload->>'host_code', payload->>'email', "
                "payload->>'name', contact_id FROM events WHERE id = %s",
                (event_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise ValueError(f"genera_poster: evento {event_id} non trovato")
    host_code, email, name, contact_id = row
    if not host_code:
        raise ValueError(f"genera_poster: host_code mancante per evento {event_id}")
    if not email:
        raise ValueError(f"genera_poster: email mancante per evento {event_id}")

    os.makedirs("/app/out", exist_ok=True)
    out_path = f"/app/out/poster_{host_code}.png"
    genera_poster_immagine(host_code, out_path)
    logger.info("genera_poster: evento %s -> %s", event_id, out_path)

    thread_id = str(event_id)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM messages WHERE thread_id = %s "
                "AND canale = 'email' AND direzione = 'out'",
                (thread_id,),
            )
            gia_inviata = cur.fetchone() is not None

            if not gia_inviata:
                nome = f"{name.split()[0]}, " if name and name.split() else ""
                corpo = CORPO_POSTER.format(nome=nome, codice=host_code)
                if not nome:
                    corpo = corpo.replace("<p>è un piacere", "<p>È un piacere", 1)
                cur.execute(
                    "INSERT INTO messages (contact_id, canale, direzione, thread_id, testo) "
                    "VALUES (%s, 'email', 'out', %s, %s)",
                    (contact_id, thread_id, corpo),
                )

    if gia_inviata:
        logger.info("genera_poster: email già inviata per evento %s, salto", event_id)
        return

    oggetto = OGGETTO_POSTER.format(codice=host_code)
    allegati = [
        (f"poster-sconto-{host_code}.png", Path(out_path).read_bytes()),
        ("poster-assistente-ai.png", POSTER_AI_PATH.read_bytes()),
    ]
    invia_email(email, oggetto, corpo, allegati)
    logger.info("genera_poster: email inviata a %s per evento %s", email, event_id)


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
