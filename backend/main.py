import json
import logging
import os

import psycopg
from fastapi import FastAPI, HTTPException, Request

app = FastAPI(title="Argo")
logger = logging.getLogger("argo")


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
    submission_id = body.get("submission_id")
    if not submission_id:
        logger.warning(
            "form.submitted senza submission_id, campi ricevuti: %s",
            sorted(body.keys()) if isinstance(body, dict) else type(body).__name__,
        )
        raise HTTPException(status_code=422, detail="submission_id mancante")

    payload = json.dumps(
        {
            "submission_id": submission_id,
            "email": body.get("email"),
            "nome": body.get("nome"),
            "codice": body.get("codice"),
        }
    )
    dedup_key = f"ghl:{submission_id}"

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
