import logging
import os
import smtplib
from email.message import EmailMessage

logger = logging.getLogger("argo.worker")


def invia_email(destinatario, oggetto, corpo_html, allegati):
    msg = EmailMessage()
    msg["Subject"] = oggetto
    msg["From"] = f'{os.environ["MAIL_FROM_NAME"]} <{os.environ["SMTP_USER"]}>'
    msg["To"] = destinatario
    msg.set_content(corpo_html, subtype="html")

    for nome_file, contenuto in allegati:
        msg.add_attachment(contenuto, maintype="image", subtype="png", filename=nome_file)

    with smtplib.SMTP(os.environ["SMTP_HOST"], int(os.environ["SMTP_PORT"])) as smtp:
        smtp.starttls()
        smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
        smtp.send_message(msg)

    logger.info("invia_email: inviata a %s (oggetto=%s)", destinatario, oggetto)


def _quota(testo):
    return "\n".join(f"> {riga}" for riga in testo.splitlines())


def invia_risposta_email(destinatario, oggetto, testo_risposta, testo_originale,
                          in_reply_to, references, reply_to):
    if not oggetto.strip().lower().startswith("re:"):
        oggetto = f"Re: {oggetto}"

    msg = EmailMessage()
    msg["Subject"] = oggetto
    msg["From"] = f'{os.environ["REPLY_FROM_NAME"]} <{os.environ["REPLY_SMTP_USER"]}>'
    msg["To"] = destinatario
    msg["Reply-To"] = reply_to
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to
    if references:
        msg["References"] = references

    corpo = f"{testo_risposta}\n\n{_quota(testo_originale)}"
    msg.set_content(corpo)

    with smtplib.SMTP(os.environ["REPLY_SMTP_HOST"], int(os.environ["REPLY_SMTP_PORT"])) as smtp:
        smtp.starttls()
        smtp.login(os.environ["REPLY_SMTP_USER"], os.environ["REPLY_SMTP_PASS"])
        smtp.send_message(msg)

    logger.info("invia_risposta_email: inviata a %s (oggetto=%s)", destinatario, oggetto)
