"""Transactional e-mail sending.

If SMTP is not configured (empty smtp_host), the link is logged instead —
convenient for local development where no mail server is available.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from ..config import get_settings

logger = logging.getLogger(__name__)


def _send(to: str, subject: str, body_text: str, body_html: str) -> None:
    settings = get_settings()
    if not settings.smtp_host:
        logger.info("[DEV] E-Mail nicht gesendet (kein SMTP konfiguriert).\n%s", body_text)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg.attach(MIMEText(body_text, "plain", "utf-8"))
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.sendmail(settings.smtp_from, [to], msg.as_string())


def send_password_reset_email(email: str, username: str, token: str) -> None:
    settings = get_settings()
    link = f"{settings.public_frontend_url}/password-reset?token={token}"
    subject = "Aristeus – Passwort zurücksetzen"
    body_text = (
        f"Hallo {username},\n\n"
        f"Du hast eine Passwort-Rücksetzung angefordert.\n\n"
        f"Link (gültig 2 Stunden):\n{link}\n\n"
        f"Falls du das nicht warst, ignoriere diese Nachricht.\n\n"
        f"– Aristeus"
    )
    body_html = f"""
    <p>Hallo <strong>{username}</strong>,</p>
    <p>Du hast eine Passwort-Rücksetzung angefordert.</p>
    <p><a href="{link}" style="font-size:16px">Passwort zurücksetzen</a></p>
    <p><small>Link gültig für 2 Stunden. Falls du das nicht warst, ignoriere diese Nachricht.</small></p>
    """
    _send(email, subject, body_text, body_html)
