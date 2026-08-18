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
