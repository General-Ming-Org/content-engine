"""Branded HTML email layout with inline logo assets (CID attachments).

Gmail inbox avatar (sender photo) is NOT controlled by email body HTML — it comes from
the sender's Google account (when using Gmail SMTP), Gravatar for the From address, or
BIMI for verified domains. We expose a square icon at /api/brand/icon.png so operators
can register the same image on Gravatar for SMTP_FROM_ADDRESS.
"""
from __future__ import annotations

import re
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from pathlib import Path
from typing import Any

from config import get_settings

settings = get_settings()

_STATIC_DIR = Path(__file__).resolve().parents[2] / "static" / "email"
ICON_CID = "content-engine-icon"
_BRAND_NAME = "Content Engine"
_ACCENT = "#5b5bd6"


def static_asset_path(name: str) -> Path:
    return _STATIC_DIR / name


def brand_icon_public_url() -> str | None:
    """Public URL for Gravatar / BIMI (set API_PUBLIC_URL)."""
    base = (settings.api_public_url or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/api/brand/icon.png"


def email_from_header() -> str:
    address = settings.smtp_from_address or settings.smtp_username
    return formataddr((_BRAND_NAME, address))


def _load_image_part(filename: str, cid: str) -> MIMEImage:
    path = static_asset_path(filename)
    data = path.read_bytes()
    subtype = "png" if filename.endswith(".png") else "svg+xml"
    part = MIMEImage(data, _subtype=subtype)
    part.add_header("Content-ID", f"<{cid}>")
    part.add_header("Content-Disposition", "inline", filename=filename)
    return part


def _plain_to_html_blocks(plain: str) -> str:
    """Turn digest plain text into simple HTML sections."""
    escaped = (
        plain.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    lines = escaped.split("\n")
    parts: list[str] = []
    for line in lines:
        if line.startswith("=" * 10):
            continue
        if line and not line.startswith(" ") and line.endswith(":") and len(line) < 80:
            parts.append(f'<p style="margin:20px 0 8px;font-size:13px;font-weight:600;color:#5b5bd6;letter-spacing:0.02em">{line}</p>')
        elif line.startswith("  - "):
            parts.append(f'<p style="margin:4px 0 4px 12px;font-size:14px;color:#333">{line[4:]}</p>')
        elif line.strip():
            parts.append(f'<p style="margin:8px 0;font-size:15px;color:#222">{line}</p>')
        else:
            parts.append('<p style="margin:0;height:8px"></p>')
    return "\n".join(parts)


def build_branded_html(
    *,
    title: str,
    subtitle: str | None = None,
    body_html: str,
    cta_url: str | None = None,
    cta_label: str | None = None,
) -> str:
    dashboard_url = (settings.app_public_url or "").strip().rstrip("/") or None

    cta_block = ""
    if cta_url and cta_label:
        cta_block = f"""
      <p style="margin:28px 0 0">
        <a href="{cta_url}" style="display:inline-block;background:{_ACCENT};color:#fff;
           padding:11px 20px;border-radius:6px;text-decoration:none;font-weight:500;font-size:14px">
          {cta_label}
        </a>
      </p>"""

    subtitle_block = ""
    if subtitle:
        subtitle_block = f'<p style="margin:0 0 20px;color:#555;font-size:15px;line-height:1.5">{subtitle}</p>'

    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>{title}</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f7;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f4f4f7;padding:32px 16px">
    <tr><td align="center">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="max-width:560px;background:#fff;border-radius:10px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.08)">
        <tr>
          <td style="padding:24px 28px 16px;border-bottom:1px solid #eee">
            <table role="presentation" cellspacing="0" cellpadding="0">
              <tr>
                <td style="vertical-align:middle;padding-right:12px">
                  <img src="cid:{ICON_CID}" width="40" height="40" alt="{_BRAND_NAME}"
                       style="display:block;border-radius:8px;width:40px;height:40px"/>
                </td>
                <td style="vertical-align:middle">
                  <span style="font-size:18px;font-weight:600;color:#1a1a2e;letter-spacing:-0.02em">{_BRAND_NAME}</span>
                </td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:28px">
            <h1 style="margin:0 0 8px;font-size:20px;font-weight:600;color:#1a1a2e">{title}</h1>
            {subtitle_block}
            <div style="color:#333;font-size:14px;line-height:1.55">
              {body_html}
            </div>
            {cta_block}
          </td>
        </tr>
        <tr>
          <td style="padding:16px 28px 24px;background:#fafafa;border-top:1px solid #eee">
            <p style="margin:0;font-size:12px;color:#999">
              {_BRAND_NAME}
              {f' · <a href="{dashboard_url}" style="color:#5b5bd6;text-decoration:none">Open dashboard</a>' if dashboard_url else ''}
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def build_branded_message(
    *,
    to_address: str,
    subject: str,
    plain_body: str,
    html_inner: str,
    title: str,
    subtitle: str | None = None,
    cta_url: str | None = None,
    cta_label: str | None = None,
) -> MIMEMultipart:
    """multipart/related message with plain + HTML and inline logo images."""
    html = build_branded_html(
        title=title,
        subtitle=subtitle,
        body_html=html_inner,
        cta_url=cta_url,
        cta_label=cta_label,
    )

    msg = MIMEMultipart("related")
    msg["Subject"] = subject
    msg["From"] = email_from_header()
    msg["To"] = to_address

    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(plain_body, "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)

    if static_asset_path("icon.png").is_file():
        msg.attach(_load_image_part("icon.png", ICON_CID))

    return msg


def digest_html_from_plain(plain: str) -> tuple[str, str]:
    """Return (title, html_body) parsed from digest plain text."""
    lines = plain.strip().split("\n")
    title = lines[0] if lines else "Content Engine"
    title = re.sub(r"^=+\s*$", "", title).strip() or "Content Engine"
    body_plain = "\n".join(lines[1:]).strip()
    return title, _plain_to_html_blocks(body_plain)
