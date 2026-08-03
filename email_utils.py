import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import dkim

from config_utils import (
    DKIM_DOMAIN,
    DKIM_ENABLED,
    DKIM_PRIVATE_KEY_PATH,
    DKIM_SELECTOR,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_SENDER_EMAIL,
    SMTP_SERVER,
)


def send_email(subject: str, body: str, to_address: str, use_dkim: bool | None = None):
    if use_dkim is None:
        use_dkim = DKIM_ENABLED

    msg = MIMEMultipart()
    msg["From"] = SMTP_SENDER_EMAIL
    msg["To"] = to_address
    msg["Subject"] = subject

    msg.attach(MIMEText(body, "html"))

    if use_dkim:
        try:
            with open(DKIM_PRIVATE_KEY_PATH, "rb") as f:
                private_key = f.read()

            sig = dkim.sign(
                message=msg.as_bytes(),
                selector=DKIM_SELECTOR.encode("utf-8"),
                domain=DKIM_DOMAIN.encode("utf-8"),
                privkey=private_key,
                include_headers=[b"To", b"From", b"Subject"],
            )
            msg["DKIM-Signature"] = sig.decode().lstrip("DKIM-Signature: ")
            logging.info("DKIM Signature added.")
        except Exception as e:
            logging.warning(f"Skipping DKIM signing: {e}")

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_SENDER_EMAIL, SMTP_PASSWORD)
        server.sendmail(SMTP_SENDER_EMAIL, to_address, msg.as_string())
        server.quit()
        logging.info("Email sent successfully!")
    except Exception as e:
        logging.error(f"Failed to send email: {e}")
