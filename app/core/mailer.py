"""SMTP dispatch for OTP and test emails (Volume 3, Chapters 20.1, 27).

Pure transport mechanics: host/port are passed in by the calling Service
(sourced from the settings table, Volume 3, Chapter 20.2); sender
credentials come from environment variables. The caller translates
failures into user-safe ValidationError messages; this module logs full
internal detail for diagnostics (Volume 3, Chapter 24.1).
"""

import logging
import smtplib
from email.message import EmailMessage

logger = logging.getLogger(__name__)


def send_email(
    smtp_host: str,
    smtp_port: int,
    from_address: str,
    app_password: str,
    to_address: str,
    subject: str,
    body: str,
) -> None:
    """Send a plain-text message over Gmail SMTP with TLS (stdlib only)."""
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_address
    message["To"] = to_address
    message.set_content(body)
    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(from_address, app_password)
            smtp.send_message(message)
    except Exception as error:
        logger.error("SMTP dispatch failed: %s", error)
        raise
