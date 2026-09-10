from __future__ import annotations

import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import date


logger = logging.getLogger(__name__)


def send_email(html_content: str, subject: str) -> bool:
    smtp_host = os.environ.get("SMTP_HOST", "")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USERNAME", "")
    smtp_pass = os.environ.get("SMTP_PASSWORD", "")
    email_to = os.environ.get("EMAIL_TO", "")

    if not all([smtp_host, smtp_user, smtp_pass, email_to]):
        logger.warning(
            "Email config incomplete. Skipping email send. "
            "Set SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD, EMAIL_TO."
        )
        _save_local_report(html_content)
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = email_to
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        logger.info(f"Email sent to {email_to}")
        return True
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        _save_local_report(html_content)
        return False


def _save_local_report(html_content: str):
    reports_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        "reports",
    )
    os.makedirs(reports_dir, exist_ok=True)
    filepath = os.path.join(reports_dir, f"report_{date.today().isoformat()}.html")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html_content)
    logger.info(f"Report saved locally: {filepath}")


def build_subject(top_count: int) -> str:
    today = date.today().isoformat()
    return f"Opportunity Scanner | {today} | {top_count} Opportunities"
