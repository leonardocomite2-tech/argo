import json
import logging
import os
import re

import psycopg
from fastapi import FastAPI, HTTPException, Request

from connectors.telegram import notifica

app = FastAPI(title="Argo")
logger = logging.getLogger("argo")

HOST_CODE_RE = re.compile(r"^[A-Z0-9]+$")
HOST_CODE_MAX_LEN = 10


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
