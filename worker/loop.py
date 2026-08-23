import hashlib
import json
import logging
import os
import time
from pathlib import Path

import psycopg

from media.poster import BASE_DIR, genera_poster as genera_poster_immagine
from connectors.imap_reader import leggi_nuove
from connectors.mailer import invia_email, invia_risposta_email
from connectors.telegram import notifica, chiedi_approvazione
from connectors.testi import (
    OGGETTO_POSTER,
    CORPO_POSTER,
    OGGETTO_CODICE_INVALIDO,
    CORPO_CODICE_INVALIDO,
    PREMESSA_CASELLA_DIVERSA,
)

POSTER_AI_PATH = BASE_DIR / "templates" / "poster_ai.png"
TESTO_MAX_LEN = 20000

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


def fail_job(job_id, tipo, errore):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET stato = 'failed', ultimo_errore = %s WHERE id = %s",
                (errore, job_id),
            )
    notifica(f"Job fallito — tipo={tipo} id={job_id} errore={errore}")


def process_next_job():
    job = claim_job()
    if job is None:
        return
    job_id, tipo, payload, tentativi = job

    fn = HANDLERS.get(tipo)
    if fn is None:
        logger.error("job %s: handler sconosciuto per tipo '%s'", job_id, tipo)
        fail_job(job_id, tipo, f"handler sconosciuto per tipo '{tipo}'")
        return

    try:
        fn(payload)
    except Exception as e:
        logger.exception("job %s (%s) fallito", job_id, tipo)
        if tentativi < 2:
            retry_job(job_id, str(e))
        else:
            fail_job(job_id, tipo, str(e))
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
    nome = f"{name.split()[0]}, " if name and name.split() else ""
    corpo = CORPO_POSTER.format(nome=nome, codice=host_code)
    if not nome:
        corpo = corpo.replace("<p>è un piacere", "<p>È un piacere", 1)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (contact_id, canale, direzione, thread_id, testo) "
                "VALUES (%s, 'email', 'out', %s, %s) "
                "ON CONFLICT (thread_id, canale, direzione) WHERE thread_id IS NOT NULL "
                "DO NOTHING RETURNING id",
                (contact_id, thread_id, corpo),
            )
            gia_inviata = cur.fetchone() is None

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
    notifica(f"Poster inviato — codice {host_code}, {name or '(senza nome)'} <{email}>")


@handler("avvisa_codice_invalido")
def avvisa_codice_invalido(payload):
    event_id = payload.get("event_id")
    if not event_id:
        raise ValueError("avvisa_codice_invalido: event_id mancante nel payload del job")

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT payload->>'email', payload->>'name', contact_id "
                "FROM events WHERE id = %s",
                (event_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise ValueError(f"avvisa_codice_invalido: evento {event_id} non trovato")
    email, name, contact_id = row
    if not email:
        raise ValueError(f"avvisa_codice_invalido: email mancante per evento {event_id}")

    thread_id = str(event_id)
    nome = f"{name.split()[0]}, " if name and name.split() else ""
    corpo = CORPO_CODICE_INVALIDO.format(nome=nome)
    if not nome:
        corpo = corpo.replace("<p>grazie", "<p>Grazie", 1)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (contact_id, canale, direzione, thread_id, testo) "
                "VALUES (%s, 'email', 'out', %s, %s) "
                "ON CONFLICT (thread_id, canale, direzione) WHERE thread_id IS NOT NULL "
                "DO NOTHING RETURNING id",
                (contact_id, thread_id, corpo),
            )
            gia_inviata = cur.fetchone() is None

    if gia_inviata:
        logger.info("avvisa_codice_invalido: email già inviata per evento %s, salto", event_id)
        return

    invia_email(email, OGGETTO_CODICE_INVALIDO, corpo, [])
    logger.info("avvisa_codice_invalido: email inviata a %s per evento %s", email, event_id)


@handler("leggi_email")
def leggi_email(payload):
    messaggi = leggi_nuove()
    logger.info("leggi_email: %d messaggi letti in questo giro", len(messaggi))

    for m in messaggi:
        message_id = m.get("message_id")
        if message_id:
            dedup_key = f"imap:{message_id}"
        else:
            testo = m.get("testo") or ""
            materiale = "|".join([
                m.get("destinatario") or "",
                m.get("mittente") or "",
                m.get("data") or "",
                m.get("oggetto") or "",
                testo[:200],
            ])
            hash_sint = hashlib.sha256(materiale.encode("utf-8")).hexdigest()
            dedup_key = f"imap-sint:{hash_sint}"
            logger.warning("leggi_email: Message-ID mancante, dedup_key sintetica %s", dedup_key)

        testo = m.get("testo") or ""
        troncato = len(testo) > TESTO_MAX_LEN
        evento_payload = json.dumps({
            "message_id": message_id,
            "mittente": m.get("mittente"),
            "destinatario": m.get("destinatario"),
            "oggetto": m.get("oggetto"),
            "testo": testo[:TESTO_MAX_LEN] if troncato else testo,
            "testo_troncato": troncato,
            "lunghezza_testo_originale": len(testo),
            "data": m.get("data"),
            "in_reply_to": m.get("in_reply_to"),
            "references": m.get("references"),
        })

        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO events (tipo, dedup_key, payload)
                    VALUES ('email.reply', %s, %s)
                    ON CONFLICT (dedup_key) DO NOTHING
                    RETURNING id
                    """,
                    (dedup_key, evento_payload),
                )
                row = cur.fetchone()
                if row is None:
                    continue
                event_id = row[0]

                cur.execute(
                    "INSERT INTO jobs (tipo, payload) VALUES ('notifica_risposta', %s)",
                    (json.dumps({"event_id": event_id}),),
                )

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs (tipo, payload, run_after) "
                "VALUES ('leggi_email', '{}', now() + interval '2 minutes')"
            )


@handler("notifica_risposta")
def notifica_risposta(payload):
    event_id = payload.get("event_id")
    if not event_id:
        raise ValueError("notifica_risposta: event_id mancante nel payload del job")

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT payload->>'mittente', payload->>'destinatario', "
                "payload->>'oggetto', payload->>'testo' FROM events WHERE id = %s",
                (event_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise ValueError(f"notifica_risposta: evento {event_id} non trovato")
    mittente, destinatario, oggetto, testo = row
    testo = (testo or "").strip()

    thread_id = str(event_id)
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (contact_id, canale, direzione, thread_id, testo) "
                "VALUES (NULL, 'email', 'in', %s, %s) "
                "ON CONFLICT (thread_id, canale, direzione) WHERE thread_id IS NOT NULL "
                "DO NOTHING RETURNING id",
                (thread_id, testo),
            )
            gia_notificata = cur.fetchone() is None

    if gia_notificata:
        logger.info("notifica_risposta: già notificata per evento %s, salto", event_id)
        return

    anteprima = testo[:400] + ("[...]" if len(testo) > 400 else "")
    testo_notifica = (
        f"📧 Nuova risposta\n"
        f"Da: {mittente}\n"
        f"A: {destinatario}\n"
        f"Oggetto: {oggetto or '(senza oggetto)'}\n\n"
        f"{anteprima}"
    )
    notifica(testo_notifica)
    logger.info("notifica_risposta: evento %s oggetto=%r notificato", event_id, oggetto)


# Stati di approvals.stato: 'in_attesa' (default, in attesa di un tocco su
# Telegram) -> 'approvata' | 'rifiutata' | 'in_modifica' (transitorio, claimato
# dal webhook mentre aspetta la reply con il testo corretto) -> 'modificata'.
# 'in_modifica' non è uno stato finale: se la reply non arriva mai resta lì,
# non torna visibile come "in_attesa" (comportamento accettato per ora, non
# c'è ancora un timeout/retry su questo ramo).
@handler("invia_risposta")
def invia_risposta(payload):
    approval_id = payload.get("approval_id")
    if not approval_id:
        raise ValueError("invia_risposta: approval_id mancante nel payload del job")

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT stato, testo_finale, message_id FROM approvals WHERE id = %s",
                (approval_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise ValueError(f"invia_risposta: approvazione {approval_id} non trovata")
    stato, testo_finale, message_id = row

    if stato not in ("approvata", "modificata"):
        logger.info(
            "invia_risposta: approvazione %s in stato '%s', nessun invio", approval_id, stato
        )
        return

    if message_id is None:
        raise ValueError(f"invia_risposta: approvazione {approval_id} senza messaggio collegato")

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.thread_id,
                       e.payload->>'mittente', e.payload->>'oggetto', e.payload->>'testo',
                       e.payload->>'message_id', e.payload->>'references'
                FROM messages m JOIN events e ON e.id = m.thread_id::int
                WHERE m.id = %s
                """,
                (message_id,),
            )
            riga = cur.fetchone()

    if riga is None:
        raise ValueError(
            f"invia_risposta: approvazione {approval_id}, messaggio {message_id} "
            "senza evento collegato"
        )
    thread_id, mittente, oggetto, testo_originale, message_id_originale, references_orig = riga

    corpo = f"{PREMESSA_CASELLA_DIVERSA}\n\n{testo_finale}"
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (contact_id, canale, direzione, thread_id, testo) "
                "VALUES (NULL, 'email', 'out', %s, %s) "
                "ON CONFLICT (thread_id, canale, direzione) WHERE thread_id IS NOT NULL "
                "DO NOTHING RETURNING id",
                (thread_id, corpo),
            )
            gia_inviata = cur.fetchone() is None

    if gia_inviata:
        logger.info("invia_risposta: già inviata per approvazione %s, salto", approval_id)
        return

    references = references_orig
    if message_id_originale:
        references = f"{references_orig} {message_id_originale}" if references_orig else message_id_originale

    reply_to = os.environ["REPLY_SMTP_USER"]
    invia_risposta_email(
        mittente, oggetto, corpo, testo_originale,
        message_id_originale, references, reply_to,
    )
    logger.info("invia_risposta: inviata per approvazione %s a %s", approval_id, mittente)
    notifica(f"Risposta inviata — approvazione #{approval_id}, oggetto: {oggetto or '(senza oggetto)'}")


@handler("test_approvazione")
def test_approvazione(payload):
    # Manuale, per collaudare il giro Approva/Modifica/Rifiuta su Telegram senza
    # classificatore. Costruisce la catena completa evento->messaggio in->approvazione
    # (quella che in produzione creerà il drafter, non ancora scritto) così
    # invia_risposta si può collaudare per intero, mittente sintetico =
    # TEST_EMAIL_DEST perché la risposta vera arrivi a noi e non a un indirizzo finto.
    # Premendo "Modifica" l'approvazione passa per lo stato transitorio
    # 'in_modifica' prima di arrivare a 'modificata' (vedi il commento sopra
    # invia_risposta per la mappa completa degli stati).
    testo_ricevuto = (
        "Buongiorno, ho ricevuto il poster con il codice sconto ma non ho capito "
        "bene come funziona la commissione per me come host: viene calcolata su "
        "ogni prenotazione che arriva con quel codice o solo sulla prima? E in "
        "che percentuale? Vorrei anche sapere quando e come viene liquidata. "
        "Grazie in anticipo, resto in attesa di un vostro riscontro."
    )
    bozza = "Bozza di prova: grazie per il messaggio, le rispondiamo al più presto."

    mittente_test = os.environ["TEST_EMAIL_DEST"]
    oggetto_test = "Domande sul codice sconto"
    message_id_test = f"<test-{int(time.time() * 1000)}@test-approvazione>"
    dedup_key = f"test-approvazione:{int(time.time() * 1000)}"

    evento_payload = json.dumps({
        "message_id": message_id_test,
        "mittente": mittente_test,
        "destinatario": os.environ.get("MAILBOX_1_USER", "campagna@example.com"),
        "oggetto": oggetto_test,
        "testo": testo_ricevuto,
        "references": None,
    })

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO events (tipo, dedup_key, payload) VALUES ('email.reply', %s, %s) "
                "RETURNING id",
                (dedup_key, evento_payload),
            )
            event_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO messages (contact_id, canale, direzione, thread_id, testo) "
                "VALUES (NULL, 'email', 'in', %s, %s) RETURNING id",
                (str(event_id), testo_ricevuto),
            )
            db_message_id = cur.fetchone()[0]

            cur.execute(
                "INSERT INTO approvals (message_id, bozza) VALUES (%s, %s) RETURNING id",
                (db_message_id, bozza),
            )
            approval_id = cur.fetchone()[0]

    contesto = {"mittente": mittente_test, "oggetto": oggetto_test, "testo_ricevuto": testo_ricevuto}
    message_id = chiedi_approvazione(approval_id, bozza, contesto)

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE approvals SET tg_message_id = %s WHERE id = %s",
                (message_id, approval_id),
            )

    logger.info(
        "test_approvazione: approvazione %s creata, messaggio Telegram %s",
        approval_id, message_id,
    )


def garantisci_leggi_email():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM jobs WHERE tipo = 'leggi_email' AND stato IN ('pending', 'running')"
            )
            if cur.fetchone() is None:
                cur.execute("INSERT INTO jobs (tipo, payload) VALUES ('leggi_email', '{}')")
                logger.warning("garantisci_leggi_email: catena leggi_email interrotta, riaccodato")


def migra_job_notifica_risposta():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE jobs SET tipo = 'notifica_risposta' "
                "WHERE tipo = 'classifica_messaggio' AND stato = 'pending'"
            )
            n = cur.rowcount
    if n:
        logger.warning("migra_job_notifica_risposta: %d job migrati da classifica_messaggio", n)


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
    migra_job_notifica_risposta()
    garantisci_leggi_email()
    while True:
        try:
            garantisci_leggi_email()
            process_next_job()
        except Exception:
            logger.exception("errore imprevisto nel loop worker")
        time.sleep(5)


if __name__ == "__main__":
    main()
