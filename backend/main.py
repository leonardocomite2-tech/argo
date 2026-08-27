import json
import logging
import os
import re
from datetime import datetime, timedelta, timezone

import psycopg
from fastapi import FastAPI, HTTPException, Request

from connectors.telegram import notifica, rispondi_callback, chiedi_testo_corretto

app = FastAPI(title="Argo")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("argo")

HOST_CODE_RE = re.compile(r"^[A-Z0-9]+$")
HOST_CODE_MAX_LEN = 10
FINESTRA_META = timedelta(hours=24)


def _normalizza_canale_dm(reply_channel):
    """reply_channel è un valore statico scritto a mano nel workflow GHL
    ("Instagram DM" / "Facebook messenger"), non deriva dal canale reale del
    messaggio — vedi nota in STATO.md. Match per sottostringa, case-insensitive."""
    valore = (reply_channel or "").strip().lower()
    if "instagram" in valore:
        return "instagram"
    if "facebook" in valore or "messenger" in valore:
        return "facebook"
    return None


def db_connect():
    return psycopg.connect(
        host="db",
        dbname="argo",
        user="argo",
        password=os.environ["PG_PASSWORD"],
    )


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/webhook/ghl/form")
async def webhook_ghl_form(request: Request):
    if request.headers.get("X-Argo-Secret") != os.environ["GHL_WEBHOOK_SECRET"]:
        raise HTTPException(status_code=401)

    body = await request.json()
    if not isinstance(body, dict):
        logger.warning(
            "form.submitted body non è un oggetto JSON, tipo ricevuto: %s",
            type(body).__name__,
        )
        raise HTTPException(
            status_code=422, detail="corpo della richiesta non è un oggetto JSON"
        )

    custom = body.get("customData")
    if not isinstance(custom, dict):
        custom = {}

    def campo(nome):
        return custom.get(nome) if custom.get(nome) is not None else body.get(nome)

    submission_id = campo("submission_id") or body.get("contact_id")
    if not submission_id:
        logger.warning(
            "form.submitted senza submission_id, campi radice: %s, campi customData: %s",
            sorted(body.keys()),
            sorted(custom.keys()) if custom else [],
        )
        raise HTTPException(status_code=422, detail="submission_id mancante")

    host_code = (campo("host_code") or "").strip().upper()
    motivo_invalido = None
    if not host_code:
        logger.warning("form.submitted host_code non valido: motivo=vuoto")
        motivo_invalido = "vuoto"
    elif not HOST_CODE_RE.match(host_code):
        logger.warning(
            "form.submitted host_code non valido: motivo=caratteri_non_validi"
        )
        notifica(
            "ALERT: webhook GHL ha ricevuto un host_code non ammesso "
            "(motivo=caratteri_non_validi) — il JS di sanificazione del form "
            "potrebbe non funzionare più."
        )
        motivo_invalido = "caratteri_non_validi"
    elif len(host_code) > HOST_CODE_MAX_LEN:
        logger.warning(
            "form.submitted host_code non valido: motivo=troppo_lungo lunghezza=%d",
            len(host_code),
        )
        notifica(
            "ALERT: webhook GHL ha ricevuto un host_code non ammesso "
            "(motivo=troppo_lungo) — il JS di sanificazione del form "
            "potrebbe non funzionare più."
        )
        motivo_invalido = "troppo_lungo"

    if motivo_invalido:
        payload = json.dumps(
            {
                "submission_id": submission_id,
                "host_code": host_code,
                "email": campo("email"),
                "name": campo("name"),
                "motivo": motivo_invalido,
            }
        )
        dedup_key = f"ghl:{submission_id}:{host_code}"

        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO events (tipo, dedup_key, payload)
                    VALUES ('form.codice_invalido', %s, %s)
                    ON CONFLICT (dedup_key) DO NOTHING
                    RETURNING id
                    """,
                    (dedup_key, payload),
                )
                row = cur.fetchone()
                if row is None:
                    return {"ok": True, "duplicato": True}
                event_id = row[0]

                cur.execute(
                    """
                    INSERT INTO jobs (tipo, payload)
                    VALUES ('avvisa_codice_invalido', %s)
                    """,
                    (json.dumps({"event_id": event_id}),),
                )

        return {"ok": True}

    payload = json.dumps(
        {
            "submission_id": submission_id,
            "host_code": host_code,
            "email": campo("email"),
            "name": campo("name"),
        }
    )
    dedup_key = f"ghl:{submission_id}:{host_code}"

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO events (tipo, dedup_key, payload)
                VALUES ('form.submitted', %s, %s)
                ON CONFLICT (dedup_key) DO NOTHING
                RETURNING id
                """,
                (dedup_key, payload),
            )
            row = cur.fetchone()
            if row is None:
                return {"ok": True, "duplicato": True}
            event_id = row[0]

            cur.execute(
                """
                INSERT INTO jobs (tipo, payload)
                VALUES ('genera_poster', %s)
                """,
                (json.dumps({"event_id": event_id}),),
            )

    return {"ok": True}


@app.post("/webhook/ghl/dm")
async def webhook_ghl_dm(request: Request):
    if request.headers.get("X-Argo-Secret") != os.environ["GHL_WEBHOOK_SECRET"]:
        raise HTTPException(status_code=401)

    adesso = datetime.now(timezone.utc)
    body = await request.json()
    if not isinstance(body, dict):
        logger.warning(
            "dm.ricevuto body non è un oggetto JSON, tipo ricevuto: %s",
            type(body).__name__,
        )
        raise HTTPException(
            status_code=422, detail="corpo della richiesta non è un oggetto JSON"
        )

    custom = body.get("customData")
    if not isinstance(custom, dict):
        custom = {}

    # Log diagnostico permanente: non esiste ancora un id univoco di messaggio/
    # conversazione nel payload GHL. `message` alla radice potrebbe contenere
    # qualcosa di più ricco di `message_body` in customData (incluso un id) —
    # va osservato su traffico reale prima di cambiare la dedup_key sotto.
    message_radice = body.get("message")
    logger.info(
        "webhook_ghl_dm: tipo di message alla radice=%s, campi=%s",
        type(message_radice).__name__,
        sorted(message_radice.keys()) if isinstance(message_radice, dict) else None,
    )

    contact_id = body.get("contact_id")
    email = body.get("email")
    first_name = body.get("first_name")
    last_name = body.get("last_name")
    message_body = custom.get("message_body")
    reply_channel = custom.get("reply_channel")
    triggered_at = custom.get("triggered_at")

    if not contact_id:
        logger.warning(
            "webhook_ghl_dm senza contact_id, campi radice: %s, campi customData: %s",
            sorted(body.keys()),
            sorted(custom.keys()),
        )
        raise HTTPException(status_code=422, detail="contact_id mancante")

    if not message_body:
        logger.info("webhook_ghl_dm: message_body vuoto (notifica di sistema, non un messaggio)")
        return {"ok": True}

    canale = _normalizza_canale_dm(reply_channel)
    if canale is None:
        logger.warning("webhook_ghl_dm: reply_channel non riconosciuto, evento scartato")
        return {"ok": True}

    scadenza = adesso + FINESTRA_META
    dedup_key = f"ghl-dm:{contact_id}:{triggered_at}"

    payload = json.dumps(
        {
            "contact_id": contact_id,
            "email": email,
            "first_name": first_name,
            "last_name": last_name,
            "message_body": message_body,
            "reply_channel": canale,
            "triggered_at": triggered_at,
            "scadenza": scadenza.isoformat(),
        }
    )

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO events (tipo, dedup_key, payload)
                VALUES ('dm.received', %s, %s)
                ON CONFLICT (dedup_key) DO NOTHING
                RETURNING id
                """,
                (dedup_key, payload),
            )
            row = cur.fetchone()
            if row is None:
                return {"ok": True, "duplicato": True}
            event_id = row[0]

            cur.execute(
                "INSERT INTO jobs (tipo, payload) VALUES ('notifica_dm', %s)",
                (json.dumps({"event_id": event_id}),),
            )

    return {"ok": True}


def _accoda_invia_risposta(cur, approval_id):
    cur.execute(
        "INSERT INTO jobs (tipo, payload) VALUES ('invia_risposta', %s)",
        (json.dumps({"approval_id": approval_id}),),
    )


def _gestisci_callback_telegram(callback_query):
    callback_query_id = callback_query.get("id")
    callback_data = callback_query.get("data") or ""
    azione, _, resto = callback_data.partition(":")

    if azione not in ("appr", "modif", "rifiu") or not resto.isdigit():
        logger.warning("webhook_telegram: callback_data non riconosciuta: %r", callback_data)
        rispondi_callback(callback_query_id, "richiesta non riconosciuta")
        return

    approval_id = int(resto)

    if azione == "appr":
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE approvals SET stato = 'approvata', testo_finale = bozza,
                    decided_at = now(), updated_at = now()
                    WHERE id = %s AND stato = 'in_attesa'
                    RETURNING id
                    """,
                    (approval_id,),
                )
                trovata = cur.fetchone() is not None
                if trovata:
                    _accoda_invia_risposta(cur, approval_id)
        rispondi_callback(callback_query_id, "Approvata ✅" if trovata else "già gestita")
        return

    if azione == "rifiu":
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE approvals SET stato = 'rifiutata', decided_at = now(), updated_at = now()
                    WHERE id = %s AND stato = 'in_attesa'
                    RETURNING id
                    """,
                    (approval_id,),
                )
                trovata = cur.fetchone() is not None
                if trovata:
                    _accoda_invia_risposta(cur, approval_id)
        rispondi_callback(callback_query_id, "Rifiutata ❌" if trovata else "già gestita")
        return

    # azione == "modif": claim atomico con lo stato transitorio 'in_modifica',
    # stessa guardia di idempotenza di appr/rifiu. Qui non basta filtrare su
    # "in_attesa" nella UPDATE finale come per gli altri due rami perché questo
    # ramo non decide l'approvazione — serve uno stato intermedio da poter
    # confrontare per evitare che un doppio callback (Telegram consegna due
    # volte, o click doppio) mandi due force-reply e sovrascriva due volte
    # tg_message_id.
    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE approvals SET stato = 'in_modifica', updated_at = now()
                WHERE id = %s AND stato = 'in_attesa'
                RETURNING id
                """,
                (approval_id,),
            )
            trovata = cur.fetchone() is not None

    if not trovata:
        rispondi_callback(callback_query_id, "già gestita")
        return

    try:
        message_id = chiedi_testo_corretto(
            f"✏️ Approvazione #{approval_id} — risponda a questo messaggio con il testo corretto:"
        )
    except Exception:
        logger.exception(
            "webhook_telegram: invio richiesta di modifica fallito per approvazione %s", approval_id
        )
        with db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE approvals SET stato = 'in_attesa', updated_at = now() "
                    "WHERE id = %s AND stato = 'in_modifica'",
                    (approval_id,),
                )
        rispondi_callback(callback_query_id, "errore, riprovi")
        return

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE approvals SET tg_message_id = %s WHERE id = %s",
                (message_id, approval_id),
            )
    rispondi_callback(callback_query_id, "In attesa del testo corretto")


def _gestisci_modifica_telegram(message):
    reply_to = message.get("reply_to_message") or {}
    reply_to_id = reply_to.get("message_id")
    testo_corretto = message.get("text")

    if not reply_to_id:
        return
    if not testo_corretto:
        logger.warning("webhook_telegram: reply senza testo, ignorata (message_id=%s)", reply_to_id)
        return

    with db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE approvals SET testo_finale = %s, stato = 'modificata',
                decided_at = now(), updated_at = now()
                WHERE tg_message_id = %s AND stato = 'in_modifica'
                RETURNING id
                """,
                (testo_corretto, reply_to_id),
            )
            row = cur.fetchone()
            if row is not None:
                _accoda_invia_risposta(cur, row[0])


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request):
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != os.environ["TELEGRAM_WEBHOOK_SECRET"]:
        raise HTTPException(status_code=401)

    body = await request.json()

    try:
        if isinstance(body, dict) and body.get("callback_query"):
            _gestisci_callback_telegram(body["callback_query"])
        elif isinstance(body, dict) and (body.get("message") or {}).get("reply_to_message"):
            _gestisci_modifica_telegram(body["message"])
    except Exception as e:
        logger.exception("webhook_telegram: errore nel processare l'update")
        notifica(f"ALERT: webhook Telegram, errore nel processare un update ({type(e).__name__})")

    return {"ok": True}
