"""Send the report through Gmail SMTP (needs a Google App Password)."""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage


def send(subject: str, html_body: str, attachments: dict[str, bytes] | None = None) -> None:
    sender = os.environ["GMAIL_ADDRESS"]
    password = os.environ["GMAIL_APP_PASSWORD"]
    recipients = [r.strip() for r in os.environ.get("REPORT_TO", sender).split(",") if r.strip()]

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"Hammor Co. Research <{sender}>"
    msg["To"] = ", ".join(recipients)
    msg.set_content("Your Hammor Co. daily report is in HTML. Open it in an email app that shows HTML.")
    msg.add_alternative(html_body, subtype="html")
    for name, data in (attachments or {}).items():
        msg.add_attachment(data, maintype="text", subtype="csv", filename=name)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(sender, password)
        s.send_message(msg)
