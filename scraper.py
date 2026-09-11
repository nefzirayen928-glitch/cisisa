#!/usr/bin/env python3
"""
CISIA TOLC/CEnT-S calendar slot monitor.

Fetches the public calendar page, parses the results table, compares it
against the last known state (state.json), and sends an email if any row
transitions into an "open / bookable" status (or its seat count goes from
0 to something positive).

Configuration (all via environment variables, see .github/workflows/check_slots.yml):
    CALENDAR_URL      - full URL to check (defaults to the CEnT-S English calendar)
    FILTER_KEYWORDS    - optional comma-separated substrings; if set, only rows whose
                          University/City text contains one of these are watched
                          (case-insensitive). Leave unset to watch every row.
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, EMAIL_TO - email delivery settings
"""

import json
import os
import smtplib
import sys
from email.mime.text import MIMEText
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DEFAULT_URL = "https://testcisia.it/calendario.php?tolc=cents&l=gb&lingua=inglese"
STATE_FILE = Path(__file__).parent / "state.json"

# Text fragments in the STATE column that mean "you cannot book this row".
CLOSED_MARKERS = ["BOOKINGS CLOSED", "NOT LONGER AVAILABLE", "NOT AVAILABLE", "CLOSED"]


def fetch_rows(url: str) -> list[dict]:
    resp = requests.get(
        url,
        timeout=30,
        headers={"User-Agent": "Mozilla/5.0 (compatible; CisiaSlotMonitor/1.0)"},
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    table = soup.find("table")
    if table is None:
        raise RuntimeError("Could not find a <table> on the page — site layout may have changed.")

    headers = [th.get_text(strip=True).upper() for th in table.find_all("th")]

    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue
        values = [td.get_text(strip=True) for td in cells]
        if len(values) < len(headers):
            continue
        row = dict(zip(headers, values))
        rows.append(row)

    return rows


def row_is_open(row: dict) -> bool:
    state = row.get("STATE", "").upper()
    if any(marker in state for marker in CLOSED_MARKERS):
        return False
    # Try to read a numeric seat count if present; treat "---" / "" as unknown (not open).
    seats_raw = row.get("SEATS", "").strip()
    if seats_raw.isdigit():
        return int(seats_raw) > 0
    # If there's no closed marker and no seat number, assume it's open
    # (covers wording like "AVAILABLE" / "OPEN" that isn't a pure number).
    return True


def row_key(row: dict) -> str:
    # Unique-enough key per row: university + city + date + format.
    return "|".join(
        row.get(k, "") for k in ("UNIVERSITY", "CITY", "DATE", "FORMAT")
    )


def matches_filter(row: dict, keywords: list[str]) -> bool:
    if not keywords:
        return True
    haystack = " ".join(
        row.get(k, "")
        for k in ("FORMAT", "UNIVERSITY", "CITY", "REGION / FOREIGN COUNTRY")
    ).lower()
    return any(k.lower() in haystack for k in keywords)


def load_previous_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def send_email(subject: str, body: str) -> None:
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASS"]
    to_addr = os.environ["EMAIL_TO"]

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_addr], msg.as_string())


def main() -> int:
    url = os.environ.get("CALENDAR_URL", DEFAULT_URL)
    keywords = [k.strip() for k in os.environ.get("FILTER_KEYWORDS", "").split(",") if k.strip()]

    rows = fetch_rows(url)
    watched = [r for r in rows if matches_filter(r, keywords)]

    if not watched:
        print("No rows matched the filter — check FILTER_KEYWORDS or the page layout.")

    previous_state = load_previous_state()
    new_state = {}
    newly_opened = []

    for row in watched:
        key = row_key(row)
        is_open = row_is_open(row)
        new_state[key] = is_open

        was_open = previous_state.get(key, False)
        if is_open and not was_open:
            newly_opened.append(row)

    save_state(new_state)

    if newly_opened:
        lines = []
        for row in newly_opened:
            lines.append(
                f"- {row.get('UNIVERSITY','?')} ({row.get('CITY','?')}) — "
                f"{row.get('FORMAT','?')} on {row.get('DATE','?')} — "
                f"seats: {row.get('SEATS','?')} — state: {row.get('STATE','?')}"
            )
        body = "New CISIA slot(s) opened:\n\n" + "\n".join(lines) + f"\n\nSource: {url}"
        print(body)
        send_email("CISIA slot alert: new booking available", body)
    else:
        print(f"Checked {len(watched)} row(s). No newly opened slots.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
