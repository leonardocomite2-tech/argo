import hashlib
import json
import logging
import os
import time
from datetime import datetime, time as dtime, timedelta, timezone
from email.utils import parseaddr
from pathlib import Path
from zoneinfo import ZoneInfo

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
FUSO_ROMA = ZoneInfo("Europe/Rome")
ORA_DIGEST = dtime(22, 0)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("argo.worker")

HANDLERS = {}


def handler(tipo):
    def deco(fn):
        HANDLERS[tipo] = fn
        return fn
    return deco


def prossimo_orario_digest():
    """Prossima occorrenza delle ORA_DIGEST in fuso Europe/Rome (oggi se non
    ancora passata, altrimenti domani). ZoneInfo gestisce da sé il cambio ora
    legale/solare."""
    adesso_roma = datetime.now(FUSO_ROMA)
    candidato = datetime.combine(adesso_roma.date(), ORA_DIGEST, tzinfo=FUSO_ROMA)
    if candidato <= adesso_roma:
        candidato += timedelta(days=1)
    return candidato


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


MOTIVO_CODICE_INVALIDO_LABEL = {
    "vuoto": "vuoto",
    "caratteri_non_validi": "caratteri non validi",
    "troppo_lungo": "troppo lungo",
}


def _nome_da_mittente(mittente):
    nome, indirizzo = parseaddr(mittente or "")
    return nome or indirizzo or "(mittente sconosciuto)"


def _tronca(testo, n=40):
    testo = testo or "(senza oggetto)"
    return testo if len(testo) <= n else testo[: n - 1].rstrip() + "…"


def _lista_con_taglio(righe, max_elementi=5):
    """Non fa assunzioni sull'ordinamento: chi chiama decide coi propri ORDER BY
    se i primi max_elementi mostrati sono i più recenti o i più vecchi."""
    if len(righe) <= max_elementi:
        return righe, 0
    return righe[:max_elementi], len(righe) - max_elementi


def componi_digest_serale(
    approvazioni, scadute, job_falliti, risposte_ricevute, risposte_inviate,
    poster, codici_rifiutati, posta
):
    titolo = f"📊 Digest serale — {datetime.now(FUSO_ROMA).strftime('%d/%m %H:%M')}"

    if not approvazioni:
        sezione_approvazioni = "✅ nessuna approvazione in attesa"
    else:
        n = len(approvazioni)
        piu_vecchia = approvazioni[0][1]
        eta_ore = (datetime.now(FUSO_ROMA) - piu_vecchia).total_seconds() / 3600
        plurale = "e" if n == 1 else "i"
        if eta_ore > 12:
            intestazione = f"⚠️ {n} approvazion{plurale} in attesa da 12h"
        else:
            intestazione = f"📋 {n} approvazion{plurale} in attesa"
        righe = [
            f"   #{id_} · {_nome_da_mittente(mittente)} — \"{_tronca(oggetto)}\""
            for id_, _, mittente, oggetto in approvazioni
        ]
        mostrate, extra = _lista_con_taglio(righe)
        if extra:
            mostrate = mostrate + [f"   e altri {extra}"]
        sezione_approvazioni = intestazione + "\n" + "\n".join(mostrate)

    if not scadute:
        sezione_scadute = "✅ nessuna approvazione scaduta"
    else:
        n = len(scadute)
        righe = [
            f"   #{id_} · {_nome_da_mittente(mittente)} — \"{_tronca(oggetto)}\""
            for id_, _, mittente, oggetto in scadute
        ]
        mostrate, extra = _lista_con_taglio(righe)
        if extra:
            mostrate = mostrate + [f"   e altri {extra}"]
        genere = "a" if n == 1 else "e"
        sezione_scadute = f"⌛ {n} approvazion{genere} scadut{genere}\n" + "\n".join(mostrate)

    if not job_falliti:
        sezione_job = "✅ nessun job fallito nelle ultime 24h"
    else:
        n = sum(c for _, c in job_falliti)
        dettaglio = ", ".join(f"{tipo}: {c}" for tipo, c in job_falliti)
        sezione_job = f"⚠️ {n} job fallit{'o' if n == 1 else 'i'}\n   {dettaglio}"

    if not risposte_ricevute:
        sezione_ricevute = "📬 nessuna risposta ricevuta"
    else:
        n = len(risposte_ricevute)
        righe = [
            f"   {_nome_da_mittente(mittente)} — {_tronca(oggetto)}"
            for mittente, oggetto, _ in risposte_ricevute
        ]
        mostrate, extra = _lista_con_taglio(righe)
        if extra:
            mostrate = mostrate + [f"   e altri {extra}"]
        genere = "a" if n == 1 else "e"
        sezione_ricevute = f"📬 {n} rispost{genere} ricevut{genere}\n" + "\n".join(mostrate)

    if not risposte_inviate:
        sezione_inviate = "📤 nessuna risposta inviata"
    else:
        n = len(risposte_inviate)
        nomi = [_nome_da_mittente(mittente) for mittente, _ in risposte_inviate]
        mostrati, extra = _lista_con_taglio(nomi)
        riga_nomi = "   → " + ", ".join(mostrati)
        if extra:
            riga_nomi += f" e altri {extra}"
        genere = "a" if n == 1 else "e"
        sezione_inviate = f"📤 {n} rispost{genere} inviat{genere}\n" + riga_nomi

    if not poster:
        sezione_poster = "🖼 nessun poster generato"
    else:
        generati = sum(1 for _, _, generato, _ in poster if generato)
        inviati = sum(1 for _, _, _, inviato in poster if inviato)
        righe = []
        for codice, nome, generato, inviato in poster:
            riga = f"   → {nome or codice} ({codice})"
            if not generato:
                riga += " — non ancora generato"
            elif not inviato:
                riga += " — non ancora inviato"
            righe.append(riga)
        mostrate, extra = _lista_con_taglio(righe)
        if extra:
            mostrate = mostrate + [f"   e altri {extra}"]
        sezione_poster = (
            f"🖼 {generati} generat{'o' if generati == 1 else 'i'}, "
            f"{inviati} inviat{'o' if inviati == 1 else 'i'}\n" + "\n".join(mostrate)
        )

    if not codici_rifiutati:
        sezione_codici = "🚫 nessun codice rifiutato"
    else:
        n = len(codici_rifiutati)
        righe = [
            f"   → {nome or '(senza nome)'} ({codice}) — "
            f"{MOTIVO_CODICE_INVALIDO_LABEL.get(motivo, motivo)}"
            for nome, codice, motivo, _ in codici_rifiutati
        ]
        mostrate, extra = _lista_con_taglio(righe)
        if extra:
            mostrate = mostrate + [f"   e altri {extra}"]
        sezione_codici = f"🚫 {n} codic{'e' if n == 1 else 'i'} rifiutat{'o' if n == 1 else 'i'}\n" + "\n".join(mostrate)

    conteggio_posta, ultima_lettura = posta
    if conteggio_posta:
        orario = ultima_lettura.astimezone(FUSO_ROMA).strftime("%H:%M")
        sezione_posta = (
            f"🔄 Posta: {conteggio_posta} lettur{'a' if conteggio_posta == 1 else 'e'} "
            f"nelle 24h, ultima alle {orario}"
        )
    else:
        sezione_posta = "🔄 Posta: 0 letture nelle 24h, ultima: mai"

    testo = "\n\n".join(
        [
            titolo,
            sezione_approvazioni,
            sezione_scadute,
            sezione_job,
            sezione_ricevute,
            sezione_inviate,
            sezione_poster,
            sezione_codici,
            sezione_posta,
        ]
    )

    if len(testo) > 3000:
        testo = testo[:2950].rstrip() + "\n\n[digest troncato per lunghezza]"

    return testo


@handler("digest_serale")
def digest_serale(payload):
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT a.id, a.updated_at, e.payload->>'mittente', e.payload->>'oggetto' "
                "FROM approvals a "
                "JOIN messages m ON m.id = a.message_id "
                "JOIN events e ON e.id = m.thread_id::int "
                "WHERE a.stato IN ('in_attesa', 'in_modifica') "
                "ORDER BY a.updated_at ASC"
            )
            approvazioni = cur.fetchall()

            cur.execute(
                "SELECT a.id, a.updated_at, e.payload->>'mittente', e.payload->>'oggetto' "
                "FROM approvals a "
                "JOIN messages m ON m.id = a.message_id "
                "JOIN events e ON e.id = m.thread_id::int "
                "WHERE a.stato = 'scaduta' AND a.updated_at >= now() - interval '24 hours' "
                "ORDER BY a.updated_at DESC"
            )
            scadute = cur.fetchall()

            cur.execute(
                "SELECT tipo, count(*) FROM jobs "
                "WHERE stato = 'failed' AND tipo != 'test_approvazione' "
                "AND created_at >= now() - interval '24 hours' "
                "GROUP BY tipo ORDER BY count(*) DESC"
            )
            job_falliti = cur.fetchall()

            cur.execute(
                "SELECT payload->>'mittente', payload->>'oggetto', created_at FROM events "
                "WHERE tipo = 'email.reply' AND created_at >= now() - interval '24 hours' "
                "ORDER BY created_at DESC"
            )
            risposte_ricevute = cur.fetchall()

            cur.execute(
                "SELECT e.payload->>'mittente', m.created_at "
                "FROM messages m JOIN events e ON e.id = m.thread_id::int "
                "WHERE m.canale = 'email' AND m.direzione = 'out' "
                "AND e.tipo = 'email.reply' "
                "AND m.created_at >= now() - interval '24 hours' "
                "ORDER BY m.created_at DESC"
            )
            risposte_inviate = cur.fetchall()

            cur.execute(
                "SELECT e.payload->>'host_code', e.payload->>'name', "
                "(COALESCE(j.stato, '') = 'done') AS generato, (m.id IS NOT NULL) AS inviato "
                "FROM events e "
                "LEFT JOIN jobs j ON j.tipo = 'genera_poster' "
                "AND (j.payload->>'event_id')::int = e.id "
                "LEFT JOIN messages m ON m.thread_id::int = e.id "
                "AND m.canale = 'email' AND m.direzione = 'out' "
                "WHERE e.tipo = 'form.submitted' "
                "AND e.created_at >= now() - interval '24 hours' "
                "ORDER BY e.created_at DESC"
            )
            poster = cur.fetchall()

            cur.execute(
                "SELECT payload->>'name', payload->>'host_code', payload->>'motivo', created_at "
                "FROM events "
                "WHERE tipo = 'form.codice_invalido' AND created_at >= now() - interval '24 hours' "
                "ORDER BY created_at DESC"
            )
            codici_rifiutati = cur.fetchall()

            cur.execute(
                "SELECT count(*), max(created_at) FROM jobs "
                "WHERE tipo = 'leggi_email' AND stato = 'done' "
                "AND created_at >= now() - interval '24 hours'"
            )
            posta = cur.fetchone()

    testo = componi_digest_serale(
        approvazioni, scadute, job_falliti, risposte_ricevute, risposte_inviate,
        poster, codici_rifiutati, posta,
    )

    # Riaccodato PRIMA dell'invio: se notifica() venisse chiamata prima e poi
    # questo INSERT fallisse, il job andrebbe in retry e reinvierebbe l'intero
    # digest da capo (notifica() non solleva mai eccezioni, quindi un retry
    # dopo un invio già avvenuto duplicherebbe il messaggio). Con l'INSERT
    # prima, un suo fallimento impedisce l'invio nello stesso tentativo; il
    # retry rifà l'INSERT (idempotente quanto quello di leggi_email) e poi invia.
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs (tipo, payload, run_after) VALUES ('digest_serale', '{}', %s)",
                (prossimo_orario_digest(),),
            )

    notifica(testo)
    logger.info("digest_serale: inviato")


def _alert_una_volta(chiave, testo):
    """Manda l'alert solo se non è già stato mandato per questa chiave
    (INSERT ... ON CONFLICT DO NOTHING RETURNING come guardia atomica,
    stesso pattern delle scritture idempotenti su `messages`)."""
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO alert_inviati (chiave) VALUES (%s) "
                "ON CONFLICT DO NOTHING RETURNING chiave",
                (chiave,),
            )
            gia_inviato = cur.fetchone() is None

    if gia_inviato:
        return
    notifica(testo)


def _controllo_approvazioni_bloccate():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT a.id, a.stato, a.updated_at, e.payload->>'mittente', e.payload->>'oggetto' "
                "FROM approvals a "
                "JOIN messages m ON m.id = a.message_id "
                "JOIN events e ON e.id = m.thread_id::int "
                "WHERE a.stato IN ('in_attesa', 'in_modifica') "
                "AND a.updated_at < now() - interval '6 hours' "
                "ORDER BY a.updated_at ASC"
            )
            righe = cur.fetchall()

    for id_, stato, updated_at, mittente, oggetto in righe:
        eta_ore = (datetime.now(FUSO_ROMA) - updated_at).total_seconds() / 3600
        testo = (
            f"⏰ Approvazione bloccata da {eta_ore:.0f}h — #{id_} · "
            f"{_nome_da_mittente(mittente)} — \"{_tronca(oggetto)}\" · stato={stato}"
        )
        if stato == "in_modifica":
            testo += "\n⚠️ in_modifica: ho premuto Modifica e non ho mai risposto col testo corretto"
        _alert_una_volta(f"appr_bloccata:{id_}", testo)


def _controllo_poster_mancante():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT e.id, e.payload->>'name', e.payload->>'host_code' "
                "FROM events e "
                "WHERE e.tipo = 'form.submitted' "
                "AND e.created_at < now() - interval '30 minutes' "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM messages m "
                "  WHERE m.thread_id::int = e.id AND m.direzione = 'out'"
                ") "
                "ORDER BY e.created_at ASC"
            )
            righe = cur.fetchall()

    for event_id, nome, host_code in righe:
        testo = (
            f"📭 Registrazione senza poster — evento #{event_id}, "
            f"{nome or '(senza nome)'} ({host_code or '(senza codice)'})"
        )
        _alert_una_volta(f"poster_mancante:{event_id}", testo)


def _controllo_volume_anomalo():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM events WHERE created_at >= now() - interval '1 hour'"
            )
            conteggio = cur.fetchone()[0]

            if conteggio <= 50:
                return

            cur.execute(
                "SELECT tipo, count(*) FROM events "
                "WHERE created_at >= now() - interval '1 hour' "
                "GROUP BY tipo ORDER BY count(*) DESC LIMIT 5"
            )
            tipi_top = cur.fetchall()

    adesso_roma = datetime.now(FUSO_ROMA)
    chiave = f"volume:{adesso_roma.strftime('%Y-%m-%d_%H')}"
    dettaglio = ", ".join(f"{tipo}: {c}" for tipo, c in tipi_top)
    testo = f"🚨 Volume anomalo — {conteggio} eventi nell'ultima ora. Tipi più frequenti: {dettaglio}"
    _alert_una_volta(chiave, testo)


def _controllo_scadenza_vicina():
    """Solo per approvazioni con scadenza (DM Instagram/Facebook, non le
    email): niente soglia delle 6h di _controllo_approvazioni_bloccate, qui
    conta quanto manca alla scadenza, non da quanto è ferma."""
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT a.id, a.scadenza, e.payload->>'mittente', e.payload->>'oggetto' "
                "FROM approvals a "
                "JOIN messages m ON m.id = a.message_id "
                "JOIN events e ON e.id = m.thread_id::int "
                "WHERE a.stato IN ('in_attesa', 'in_modifica') "
                "AND a.scadenza IS NOT NULL "
                "AND a.scadenza <= now() + interval '2 hours' "
                "ORDER BY a.scadenza ASC"
            )
            righe = cur.fetchall()

    adesso = datetime.now(timezone.utc)
    for id_, scadenza, mittente, oggetto in righe:
        etichetta = f"#{id_} · {_nome_da_mittente(mittente)} — \"{_tronca(oggetto)}\""

        if scadenza > adesso:
            minuti = int((scadenza - adesso).total_seconds() // 60)
            testo = f"⚠️ Approvazione in scadenza — {etichetta} · scade tra {minuti}min"
            _alert_una_volta(f"scadenza_vicina:{id_}", testo)
            continue

        # Scadenza già passata e mai toccata: il sistema la chiude da sé
        # invece di lasciarla visibile come ancora azionabile. Alert PRIMA
        # della UPDATE, non dopo: una volta che la UPDATE va a buon fine la
        # riga esce dal WHERE sopra e i cicli successivi non la rivedono più
        # — se l'alert fosse dopo e il processo si fermasse in mezzo,
        # l'alert non partirebbe mai. Mandandolo prima: se il processo si
        # ferma fra le due istruzioni, il ciclo seguente la ritrova ancora
        # 'in_attesa'/'in_modifica', l'alert fa no-op (chiave già presente)
        # e la UPDATE viene ritentata finché non va a buon fine.
        testo = (
            f"⌛ Finestra chiusa senza risposta — {etichetta} · nessuno ha "
            "approvato/rifiutato in tempo, chiusa automaticamente"
        )
        _alert_una_volta(f"scaduta_auto:{id_}", testo)

        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE approvals SET stato = 'scaduta', updated_at = now()
                    WHERE id = %s AND stato IN ('in_attesa', 'in_modifica')
                    """,
                    (id_,),
                )


@handler("controlli_periodici")
def controlli_periodici(payload):
    for controllo in (
        _controllo_approvazioni_bloccate,
        _controllo_poster_mancante,
        _controllo_volume_anomalo,
        _controllo_scadenza_vicina,
    ):
        try:
            controllo()
        except Exception:
            logger.exception("controlli_periodici: %s fallito", controllo.__name__)

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO jobs (tipo, payload, run_after) "
                "VALUES ('controlli_periodici', '{}', now() + interval '15 minutes')"
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
# c'è ancora un timeout/retry su questo ramo) — a meno che l'approvazione
# abbia una `scadenza` (DM Instagram/Facebook, non le email): in quel caso
# _controllo_scadenza_vicina la chiude in 'scaduta' da sola quando la
# scadenza passa senza risposta.
# 'scaduta' è un ulteriore stato terminale, raggiungibile da due punti:
# _controllo_scadenza_vicina (mai approvata/rifiutata/modificata in tempo) o
# invia_risposta qui sotto (approvata/modificata ma la finestra si è chiusa
# prima che l'invio partisse). Non si applica alle email (scadenza NULL).
@handler("invia_risposta")
def invia_risposta(payload):
    approval_id = payload.get("approval_id")
    if not approval_id:
        raise ValueError("invia_risposta: approval_id mancante nel payload del job")

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT stato, testo_finale, message_id, scadenza FROM approvals WHERE id = %s",
                (approval_id,),
            )
            row = cur.fetchone()

    if row is None:
        raise ValueError(f"invia_risposta: approvazione {approval_id} non trovata")
    stato, testo_finale, message_id, scadenza = row

    if stato not in ("approvata", "modificata"):
        logger.info(
            "invia_risposta: approvazione %s in stato '%s', nessun invio", approval_id, stato
        )
        return

    if scadenza is not None and scadenza < datetime.now(timezone.utc):
        # Alert PRIMA della UPDATE, non dopo: se il processo muore fra le due
        # istruzioni e il job va in retry, la SELECT in cima rilegge stato già
        # 'scaduta' e il ramo "nessun invio" sopra esce subito — senza mai
        # arrivare qui, quindi un alert successivo alla UPDATE rischierebbe di
        # non partire mai. Mandandolo prima: _alert_una_volta fa no-op se la
        # chiave è già presente (nessun doppio alert) e la UPDATE viene
        # ritentata ad ogni retry finché non va a buon fine.
        _alert_una_volta(
            f"scaduta:{approval_id}",
            f"⌛ Finestra di risposta chiusa — approvazione #{approval_id} approvata/modificata "
            "ma non inviata in tempo: la finestra della piattaforma si è chiusa, va gestita a mano.",
        )
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE approvals SET stato = 'scaduta', updated_at = now()
                    WHERE id = %s AND stato IN ('approvata', 'modificata')
                    """,
                    (approval_id,),
                )
        logger.info(
            "invia_risposta: approvazione %s scaduta prima dell'invio, nessun invio", approval_id
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


def garantisci_controlli_periodici():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM jobs WHERE tipo = 'controlli_periodici' AND stato IN ('pending', 'running')"
            )
            if cur.fetchone() is None:
                cur.execute("INSERT INTO jobs (tipo, payload) VALUES ('controlli_periodici', '{}')")
                logger.warning("garantisci_controlli_periodici: catena interrotta, riaccodato")


def garantisci_digest_serale():
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM jobs WHERE tipo = 'digest_serale' AND stato IN ('pending', 'running')"
            )
            if cur.fetchone() is None:
                adesso_roma = datetime.now(FUSO_ROMA)
                if adesso_roma.time() >= ORA_DIGEST:
                    # le 22:00 di oggi sono già passate senza un digest riuscito
                    # (es. il job precedente è finito 'failed'): recupera subito
                    # invece di aspettare domani, meglio un digest in ritardo che
                    # nessun digest. Unico caso in cui run_after NON è le 22:00 fisse.
                    run_after = adesso_roma
                    motivo = "recupero in ritardo (22:00 di oggi già passate)"
                else:
                    run_after = prossimo_orario_digest()
                    motivo = "programmazione regolare alle 22:00"
                cur.execute(
                    "INSERT INTO jobs (tipo, payload, run_after) VALUES ('digest_serale', '{}', %s)",
                    (run_after,),
                )
                logger.warning(
                    "garantisci_digest_serale: catena interrotta, riaccodato per %s (%s)",
                    run_after, motivo,
                )


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
    garantisci_digest_serale()
    garantisci_controlli_periodici()
    while True:
        try:
            garantisci_leggi_email()
            garantisci_digest_serale()
            garantisci_controlli_periodici()
            process_next_job()
        except Exception:
            logger.exception("errore imprevisto nel loop worker")
        time.sleep(5)


if __name__ == "__main__":
    main()
