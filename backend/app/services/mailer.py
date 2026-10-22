import base64
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any

import aiosmtplib
import msal

M365_SMTP_SCOPE = "https://outlook.office365.com/.default"


class MailError(Exception):
    pass


def _m365_token(cfg: dict[str, Any]) -> str:
    app = msal.ConfidentialClientApplication(
        cfg["oauth_client_id"],
        authority=f"https://login.microsoftonline.com/{cfg['oauth_tenant_id']}",
        client_credential=cfg["oauth_client_secret"],
    )
    result = app.acquire_token_for_client(scopes=[M365_SMTP_SCOPE])
    if "access_token" not in result:
        raise MailError(result.get("error_description") or "Could not get an OAuth2 token")
    return result["access_token"]


def build_message(cfg: dict[str, Any], to: str, subject: str, text: str, html: str | None = None) -> EmailMessage:
    if not cfg.get("from_address"):
        raise MailError("No sender address configured")
    msg = EmailMessage()
    msg["From"] = formataddr((cfg.get("from_name") or "", cfg["from_address"]))
    msg["To"] = to
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=cfg["from_address"].split("@")[-1])
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    return msg


async def send_mail(cfg: dict[str, Any], to: str, subject: str, text: str, html: str | None = None) -> None:
    if not cfg.get("host"):
        raise MailError("No SMTP server configured")
    msg = build_message(cfg, to, subject, text, html)
    security = cfg.get("security", "starttls")
    smtp = aiosmtplib.SMTP(
        hostname=cfg["host"],
        port=int(cfg.get("port") or 587),
        use_tls=security == "ssl",
        start_tls=security == "starttls",
        validate_certs=bool(cfg.get("verify_tls", True)),
        timeout=20,
    )
    try:
        await smtp.connect()
        method = cfg.get("auth_method", "password")
        if method == "password" and cfg.get("username"):
            await smtp.login(cfg["username"], cfg.get("password") or "")
        elif method == "oauth2_m365":
            token = _m365_token(cfg)
            user = cfg.get("username") or cfg["from_address"]
            auth = base64.b64encode(f"user={user}\x01auth=Bearer {token}\x01\x01".encode()).decode()
            response = await smtp.execute_command(b"AUTH", b"XOAUTH2", auth.encode())
            if response.code != 235:
                raise MailError(f"XOAUTH2 login failed: {response.code} {response.message}")
        await smtp.send_message(msg)
    except aiosmtplib.SMTPException as exc:
        raise MailError(str(exc)) from exc
    except OSError as exc:
        raise MailError(f"Connection failed: {exc}") from exc
    finally:
        if smtp.is_connected:
            try:
                await smtp.quit()
            except aiosmtplib.SMTPException:
                pass
