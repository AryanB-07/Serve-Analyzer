"""Outgoing email: account verification, password resets and account notices.

SMTP in production (any provider; Gmail works with an app password). Without an
SMTP host, development writes each message to data_dir/outbox as an .eml file and
logs its links, so the flows can be clicked through locally without sending mail.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
import uuid
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formatdate, make_msgid
from html import escape
from pathlib import Path
from typing import Protocol

from .settings import Settings

log = logging.getLogger("serve_api.mailer")

APP_NAME = "Serve Analyzer"


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    text: str
    html: str


class Mailer(Protocol):
    def send(self, message: Email) -> None: ...


def _build(message: Email, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = f"{APP_NAME} <{sender}>" if sender else APP_NAME
    msg["To"] = message.to
    msg["Subject"] = message.subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or None)
    msg.set_content(message.text)
    msg.add_alternative(message.html, subtype="html")
    return msg


class SmtpMailer:
    """Encryption follows ``Settings.smtp_mode``: implicit TLS ("ssl", port 465 by default),
    STARTTLS (any other port, e.g. Gmail's or Brevo's 587), or none for a local relay."""

    def __init__(self, settings: Settings, timeout_s: float = 20.0) -> None:
        self.settings, self.timeout_s = settings, timeout_s

    def send(self, message: Email) -> None:
        s = self.settings
        mode = s.smtp_mode
        context = ssl.create_default_context()
        if mode == "ssl":
            server: smtplib.SMTP = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=self.timeout_s,
                                                    context=context)
        else:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=self.timeout_s)
        with server:
            if mode == "starttls":
                server.starttls(context=context)
            if s.smtp_username:
                server.login(s.smtp_username, s.smtp_password)
            server.send_message(_build(message, s.sender))


class OutboxMailer:
    """Development stand-in: writes messages to a folder instead of sending them."""

    def __init__(self, folder: Path, sender: str = "") -> None:
        self.folder, self.sender = folder, sender

    def send(self, message: Email) -> None:
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{uuid.uuid4().hex}.eml"
        path.write_bytes(bytes(_build(message, self.sender or "no-reply@localhost")))
        log.warning("email to %s (%s) written to %s:\n%s", message.to, message.subject, path, message.text)


def make_mailer(settings: Settings) -> Mailer:
    if settings.smtp_host:
        return SmtpMailer(settings)
    return OutboxMailer(settings.outbox_dir, settings.sender)


def send_quietly(mailer: Mailer, message: Email) -> None:
    """For background tasks: a failed send is logged, never raised into the request."""
    try:
        mailer.send(message)
    except Exception:
        log.exception("could not send %r to %s", message.subject, message.to)


# --- the messages ----------------------------------------------------------------------

def _html(paragraphs: list[str], link: tuple[str, str] | None = None) -> str:
    body = "".join(f"<p>{p}</p>" for p in paragraphs[:1])
    if link:
        label, url = link
        body += (f'<p><a href="{escape(url)}" style="display:inline-block;padding:10px 18px;'
                 f'background:#2a6fc9;color:#fff;border-radius:8px;text-decoration:none;'
                 f'font-weight:600">{escape(label)}</a></p>'
                 f'<p style="color:#4f5d73;font-size:13px">Or paste this link into your browser:<br>'
                 f'{escape(url)}</p>')
    body += "".join(f"<p>{p}</p>" for p in paragraphs[1:])
    return (f'<div style="font-family:system-ui,sans-serif;font-size:15px;line-height:1.5;'
            f'color:#0e1726;max-width:520px">{body}</div>')


def verification_email(to: str, url: str) -> Email:
    return Email(
        to=to,
        subject=f"Confirm your email for {APP_NAME}",
        text=(f"Confirm your email address to start analysing serves:\n\n{url}\n\n"
              "The link works for 24 hours. If you didn't create an account, ignore this email."),
        html=_html(["Confirm your email address to start analysing serves.",
                    "The link works for 24 hours. If you didn't create an account, ignore this email."],
                   ("Confirm email", url)),
    )


def password_reset_email(to: str, url: str) -> Email:
    return Email(
        to=to,
        subject=f"Reset your {APP_NAME} password",
        text=(f"Someone asked to reset the password for this account. To choose a new one, open:\n\n"
              f"{url}\n\nThe link works for 1 hour and can be used once. If it wasn't you, ignore "
              "this email: your password stays the same."),
        html=_html(["Someone asked to reset the password for this account.",
                    "The link works for 1 hour and can be used once. If it wasn't you, ignore this "
                    "email: your password stays the same."],
                   ("Choose a new password", url)),
    )


def password_changed_email(to: str, app_url: str) -> Email:
    return Email(
        to=to,
        subject=f"Your {APP_NAME} password was changed",
        text=(f"The password for this account was just changed, and every device was signed out.\n\n"
              f"If that wasn't you, reset your password now: {app_url}/forgot-password"),
        html=_html(["The password for this account was just changed, and every device was signed out.",
                    f'If that wasn\'t you, <a href="{escape(app_url)}/forgot-password">reset your '
                    "password now</a>."]),
    )


def account_deleted_email(to: str) -> Email:
    return Email(
        to=to,
        subject=f"Your {APP_NAME} account was deleted",
        text=("Your account and all of its videos and analyses have been deleted. "
              "This can't be undone. Thanks for trying Serve Analyzer."),
        html=_html(["Your account and all of its videos and analyses have been deleted. "
                    "This can't be undone.", "Thanks for trying Serve Analyzer."]),
    )
