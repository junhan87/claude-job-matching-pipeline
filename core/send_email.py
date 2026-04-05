"""
Send job scan results as an HTML email with clickable URLs.

Reads plain-text output from OUTPUT_FILE (default: /tmp/output.txt),
converts it to HTML, and sends via Gmail SMTP using an App Password.

Required environment variables:
  SMTP_FROM       - sender Gmail address (e.g. you@gmail.com)
  SMTP_PASSWORD   - Gmail App Password (16 chars, no spaces)
  NOTIFY_EMAIL    - recipient address

Optional:
  OUTPUT_FILE     - path to captured output (default: /tmp/output.txt)
"""

import os
import re
import html
import smtplib
import sys
import tempfile
from datetime import date
from pathlib import Path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

_default_output = str(Path(tempfile.gettempdir()) / "output.txt")
OUTPUT_FILE  = os.getenv("OUTPUT_FILE", _default_output)
SMTP_FROM    = os.getenv("SMTP_FROM", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
NOTIFY_EMAIL = os.getenv("NOTIFY_EMAIL", "")

# Rank colour badges
RANK_COLOURS = {
    "HIGH":   ("#1a7f37", "#d4eeda"),
    "MEDIUM": ("#9a6700", "#fff3cd"),
    "LOW":    ("#6e6e6e", "#f0f0f0"),
    "SKIP":   ("#cc0000", "#fde8e8"),
}

_URL_RE = re.compile(r'(https?://\S+)')
_RANK_RE = re.compile(r'\[(HIGH|MEDIUM|LOW|SKIP)\]')


def _linkify(text: str) -> str:
    """Replace bare URLs with <a> tags. Input is already HTML-escaped."""
    # URLs were HTML-escaped so & → &amp; etc; match the escaped form
    return _URL_RE.sub(
        lambda m: f'<a href="{m.group(1)}" style="color:#0969da">{m.group(1)}</a>',
        text,
    )


def _rank_badge(rank: str) -> str:
    fg, bg = RANK_COLOURS.get(rank, ("#333", "#eee"))
    return (
        f'<span style="background:{bg};color:{fg};font-weight:bold;'
        f'padding:1px 6px;border-radius:3px;font-size:0.85em">{rank}</span>'
    )


def _line_to_html(raw_line: str) -> str:
    """Convert one plain-text line to an HTML line, linkifying URLs and badging ranks."""
    escaped = html.escape(raw_line)
    # Replace [RANK] tokens with coloured badges
    escaped = _RANK_RE.sub(lambda m: _rank_badge(m.group(1)), escaped)
    # Make URLs clickable
    escaped = _linkify(escaped)
    return escaped


def _section_style(line: str) -> str | None:
    """Return a CSS class hint for section-header lines, or None for regular lines."""
    stripped = line.strip()
    if stripped.startswith("===") and stripped.endswith("==="):
        return "section-header"
    if stripped == "=" * 60 or stripped == "CONSOLIDATED RANKING":
        return "rank-header"
    return None


def build_html(plain_text: str) -> str:
    lines = plain_text.splitlines()
    body_rows: list[str] = []

    for line in lines:
        hint = _section_style(line)
        content = _line_to_html(line)
        if hint == "section-header":
            body_rows.append(
                f'<div style="margin-top:18px;font-weight:bold;font-size:1.05em;'
                f'color:#0550ae;border-bottom:1px solid #d0d7de;padding-bottom:4px">'
                f'{content}</div>'
            )
        elif hint == "rank-header":
            body_rows.append(
                f'<div style="margin-top:18px;font-weight:bold;color:#24292f">{content}</div>'
            )
        elif not line.strip():
            body_rows.append('<div style="height:6px"></div>')
        else:
            body_rows.append(f'<div style="white-space:pre-wrap;overflow-wrap:break-word">{content}</div>')

    inner = "\n".join(body_rows)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Job Scan Results</title>
</head>
<body style="margin:0;padding:0;background:#f6f8fa;font-family:monospace,monospace;font-size:13px;color:#24292f">
<div style="max-width:800px;margin:24px auto;background:#ffffff;border:1px solid #d0d7de;
            border-radius:6px;padding:24px 28px">
  <h2 style="margin:0 0 16px;font-family:sans-serif;font-size:1.2em;color:#0550ae">
    Job Scan Results &mdash; {date.today().strftime("%d %b %Y")}
  </h2>
  {inner}
  <hr style="margin-top:24px;border:none;border-top:1px solid #d0d7de">
  <p style="margin:8px 0 0;font-family:sans-serif;font-size:11px;color:#6e7781">
    Sent by job-scanner &bull; GitHub Actions
  </p>
</div>
</body>
</html>"""


def send(html_body: str, plain_body: str) -> None:
    subject = f"Job Scan Results — {date.today().strftime('%d %b %Y')}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = SMTP_FROM
    msg["To"] = NOTIFY_EMAIL
    msg.attach(MIMEText(plain_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SMTP_FROM, SMTP_PASSWORD)
        smtp.sendmail(SMTP_FROM, NOTIFY_EMAIL, msg.as_string())


def main() -> None:
    missing = [v for v in ("SMTP_FROM", "SMTP_PASSWORD", "NOTIFY_EMAIL") if not os.getenv(v)]
    if missing:
        print(f"send_email: missing env vars: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    try:
        with open(OUTPUT_FILE, encoding="utf-8", errors="replace") as f:
            plain_body = f.read()
    except FileNotFoundError:
        print(f"send_email: output file not found: {OUTPUT_FILE}", file=sys.stderr)
        sys.exit(1)

    if not plain_body.strip():
        print("send_email: output file is empty, skipping.", file=sys.stderr)
        sys.exit(0)

    html_body = build_html(plain_body)
    send(html_body, plain_body)
    print(f"send_email: sent to {NOTIFY_EMAIL}")


if __name__ == "__main__":
    main()
