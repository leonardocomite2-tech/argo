import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger("argo.ghl")

API_URL = "https://services.leadconnectorhq.com/conversations/messages"


def invia_messaggio(contact_id, tipo, testo):
    """POST a GHL per inviare un DM (IG/FB) su una conversazione esistente.
    `tipo` è passato così com'è (atteso "IG" o "FB") senza validazione: se il
    valore è sbagliato lo scopriamo dall'errore dell'API. Non include `status`
    nel body: la doc GHL lo dà come obbligatorio ma è semanticamente strano
    su un endpoint di invio — se serve davvero lo scopriamo dall'errore.
    Ritorna (conversation_id, message_id) dal body di risposta.
    Solleva RuntimeError con status code e body completo se non è 2xx.
    Connettore di solo invio diretto: nessuna integrazione con `approvals`."""
    token = os.environ["GHL_API_TOKEN"]
    version = os.environ["GHL_API_VERSION"]

    data = json.dumps({
        "type": tipo,
        "contactId": contact_id,
        "message": testo,
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=data,
        headers={
            # La doc GHL mostra il token nudo, ma l'API vuole il prefisso
            # "Bearer ": senza, risponde 401 "Invalid JWT". Verificato in produzione.
            "Authorization": f"Bearer {token}",
            "Version": version,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "Argo/1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            corpo_risposta = resp.read()
    except urllib.error.HTTPError as e:
        corpo_errore = e.read().decode("utf-8", errors="replace").replace(token, "***")
        if e.code == 401:
            logger.error(
                "invia_messaggio: 401 con Authorization senza prefisso 'Bearer ' "
                "(contact_id=%s, tipo=%s) — riprovare a mano con 'Bearer ' davanti "
                "al token per capire se è quello lo schema atteso da GHL",
                contact_id, tipo,
            )
        logger.error("invia_messaggio: risposta di errore da GHL, status=%s body=%s", e.code, corpo_errore)
        raise RuntimeError(f"invia_messaggio fallita: status={e.code} body={corpo_errore}") from None
    except Exception as e:
        messaggio = str(e).replace(token, "***")
        logger.error("invia_messaggio: chiamata a GHL fallita (%s): %s", type(e).__name__, messaggio)
        raise RuntimeError(f"invia_messaggio fallita ({type(e).__name__}): {messaggio}") from None

    testo_risposta = corpo_risposta.decode("utf-8", errors="replace")
    logger.info("invia_messaggio: risposta OK da GHL, body=%s", testo_risposta)

    risultato = json.loads(corpo_risposta)
    return risultato.get("conversationId"), risultato.get("messageId")
