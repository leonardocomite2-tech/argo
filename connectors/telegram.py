import json
import logging
import os
import urllib.request

logger = logging.getLogger("argo.telegram")

API_BASE = "https://api.telegram.org"


def notifica(testo):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("notifica: TELEGRAM_TOKEN o TELEGRAM_CHAT_ID mancanti, notifica non inviata")
        return

    url = f"{API_BASE}/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": testo}).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception as e:
        messaggio = str(e).replace(token, "***")
        logger.error("notifica: invio a Telegram fallito (%s): %s", type(e).__name__, messaggio)
