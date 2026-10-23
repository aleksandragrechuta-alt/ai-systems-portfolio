"""Send rules from the Mur Mur outreach pipeline (excerpt).

These are the checks that decide whether an approved email may go out now,
and how the inbox is read afterwards. They are copied from the live pipeline
(outreach_pipeline.py, v6, live since September 2026). The full pipeline is
about 2,600 lines and private, because it works on real contacts.

Changes for this excerpt: imports and three settings moved to the top, and
send_decision() at the end condenses the order of checks in the pipeline's
send_approved(), without the Google Sheets and mail-server calls.
"""

from __future__ import annotations

import email.utils
import re
from datetime import datetime, timezone

IGNORE_SEND_WINDOW = False      # a switch for manual test runs in the pipeline
RUN_HOURS_UTC = range(6, 20)    # the robot runs hourly, 06:00-19:00 UTC
DAILY_SEND_CAP = 10             # fallback; the live limit is a setting in the sheet


# ---- Writing rules: every AI draft is checked before a person can approve it

BANNED_WORDS = [
    "handcrafted", "handmade", "made by hand", "3d printed", "rgb",
    "luxury", "high-end", "high end", "best quality", "unique", "amazing",
    "stunning", "gorgeous", "limited offer", "buy now", "don't miss out",
    "elevate your space", "we are excited to introduce", "we are proud to present",
    "i immediately felt the connection", "i wanted to reach out",
]


def _normalise(text: str) -> str:
    return text.lower().replace("\u2019", "'").replace("\u2018", "'")


def check_text_rules(text: str, words: list[str]) -> list[str]:
    problems = []
    if re.search(r"[—–]", text):
        problems.append("contains an em or en dash")
    lower = _normalise(text)
    for w in words:
        if w in lower:
            problems.append(f"banned word: {w}")
    return problems


# ---- Send window: approved emails go out in the recipient's local morning

def _plain(x: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", x or "") if not unicodedata.combining(c)).lower().strip()


COUNTRY_TZ = {
    "spain": "Europe/Madrid", "andorra": "Europe/Andorra", "portugal": "Europe/Lisbon", "france": "Europe/Paris",
    "monaco": "Europe/Monaco", "italy": "Europe/Rome", "poland": "Europe/Warsaw", "germany": "Europe/Berlin",
    "netherlands": "Europe/Amsterdam", "belgium": "Europe/Brussels", "luxembourg": "Europe/Luxembourg",
    "denmark": "Europe/Copenhagen", "sweden": "Europe/Stockholm", "norway": "Europe/Oslo",
    "finland": "Europe/Helsinki", "greece": "Europe/Athens", "austria": "Europe/Vienna",
    "switzerland": "Europe/Zurich", "united kingdom": "Europe/London", "uk": "Europe/London",
    "england": "Europe/London", "scotland": "Europe/London", "ireland": "Europe/Dublin",
    "czech republic": "Europe/Prague", "czechia": "Europe/Prague", "hungary": "Europe/Budapest",
    "romania": "Europe/Bucharest", "croatia": "Europe/Zagreb", "slovenia": "Europe/Ljubljana",
    "slovakia": "Europe/Bratislava", "estonia": "Europe/Tallinn", "latvia": "Europe/Riga",
    "lithuania": "Europe/Vilnius", "bulgaria": "Europe/Sofia", "cyprus": "Asia/Nicosia", "malta": "Europe/Malta",
    "iceland": "Atlantic/Reykjavik", "turkey": "Europe/Istanbul", "usa": "America/New_York",
    "united states": "America/New_York", "canada": "America/Toronto", "mexico": "America/Mexico_City",
    "argentina": "America/Argentina/Buenos_Aires", "chile": "America/Santiago", "colombia": "America/Bogota",
    "peru": "America/Lima", "uruguay": "America/Montevideo", "costa rica": "America/Costa_Rica",
    "brazil": "America/Sao_Paulo", "japan": "Asia/Tokyo", "south korea": "Asia/Seoul", "korea": "Asia/Seoul",
    "australia": "Australia/Sydney", "new zealand": "Pacific/Auckland", "uae": "Asia/Dubai",
    "united arab emirates": "Asia/Dubai", "singapore": "Asia/Singapore", "hong kong": "Asia/Hong_Kong",
}
CANARY_CITIES = ("tenerife", "las palmas", "gran canaria", "lanzarote", "fuerteventura", "la palma", "canarias")
DAY_NAMES = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def contact_tz(r: dict):
    from zoneinfo import ZoneInfo
    country, city = _plain(r.get("Country")), _plain(r.get("City"))
    if country == "spain" and any(c in city for c in CANARY_CITIES):
        return ZoneInfo("Atlantic/Canary")
    return ZoneInfo(COUNTRY_TZ.get(country, "Europe/Madrid"))


def parse_send_window(text: str):
    """'Mon-Fri 09:00-12:00' -> ({0..4}, 9.0, 12.0). Empty or unreadable -> None (no window)."""
    t = (text or "").lower()
    hours = re.search(r"(\d{1,2})(?:[:.h](\d{2}))?\s*-\s*(\d{1,2})(?:[:.h](\d{2}))?\s*$", t.strip())
    if not hours:
        return None
    start = int(hours.group(1)) + int(hours.group(2) or 0) / 60
    end = int(hours.group(3)) + int(hours.group(4) or 0) / 60
    days = set(range(7))
    d = re.search(r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\s*-\s*(mon|tue|wed|thu|fri|sat|sun)", t)
    if d:
        a, b = DAY_NAMES.index(d.group(1)), DAY_NAMES.index(d.group(2))
        days = {(a + i) % 7 for i in range(((b - a) % 7) + 1)}
    return days, start, end


def in_send_window(r: dict, voice: dict, now: datetime | None = None) -> tuple[bool, str]:
    """(ok to send now, human description of the window for this contact)."""
    window = parse_send_window(voice.get("Send window", ""))
    if IGNORE_SEND_WINDOW or not window:
        return True, ""
    days, start, end = window
    tz = contact_tz(r)
    now = now or datetime.now(timezone.utc)
    local = now.astimezone(tz)
    desc = f"{voice['Send window']} their time ({tz.key})"
    # A window no hourly run can ever reach (e.g. Asia) would hold the email forever: then send anytime.
    reachable = any(start <= now.replace(hour=h, minute=5).astimezone(tz).hour + 5 / 60 < end for h in RUN_HOURS_UTC)
    if not reachable:
        return True, ""
    return local.weekday() in days and start <= local.hour + local.minute / 60 < end, desc


# ---- Who may be emailed: only a verified address, and never the same company twice

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,6}")


def send_address(r: dict) -> str:
    """The address the Email cell starts with ('gallery@x.com (alt: ...)' -> 'gallery@x.com').
    '' when the cell doesn't START with one: 'Not found (form only; listings suggest info@x.com,
    unverified)' must never be mailed, because that address was never verified on their site."""
    m = EMAIL_RE.match((r.get("Email") or "").strip())
    return m.group(0) if m else ""


GENERIC_MAIL = re.compile(
    r"^(gmail|googlemail|hotmail|outlook|live|msn|yahoo|ymail|icloud|me|mac|aol|proton|protonmail|gmx|web|"
    r"t-online|orange|wanadoo|free|sfr|laposte|libero|virgilio|naver|bigpond|telenet|skynet|hotmail\.co|btinternet)\.")


def company_key(r: dict) -> str:
    """Website domain if known, else the email domain (unless it's a generic provider like gmail)."""
    from urllib.parse import urlparse
    email_addr = (r.get("Email") or "").strip().lower()
    email_dom = email_addr.split("@", 1)[1] if "@" in email_addr else ""
    if GENERIC_MAIL.match(email_dom):
        email_dom = ""
    site = (r.get("Website") or "").strip()
    if site.startswith("http"):
        u = urlparse(site)
        host = u.netloc.lower().removeprefix("www.")
        if host:
            # Country editions on one domain (elledecor.com/es vs /it) are different companies,
            # unless the email is on the site's own domain (fleux.com/en + @fleux.com = Fleux).
            first = u.path.strip("/").split("/")[0].lower()
            if len(first) == 2 and first.isalpha() and not email_dom.endswith(host):
                return f"{host}/{first}"
            return host
    return email_dom


CONTACTED = ("Sent", "Replied", "Follow-up Draft", "Follow-up APPROVED", "Follow-up Sent")


def already_contacted(r: dict, tab_name: str, company_index: dict):
    key = company_key(r)
    for o in company_index.get(key, []) if key else []:
        if (o["tab"], o["row"]) != (tab_name, r["_row"]) and o["status"] in CONTACTED:
            return o
    return None


# ---- Reading the inbox: bounces and automatic replies are not real replies

BOUNCE_FROM = re.compile(r"mailer-daemon|postmaster|mail delivery", re.I)
BOUNCE_SUBJECT = re.compile(r"undeliver|delivery status notification|returned mail|mail delivery failed|"
                            r"failure notice|delivery failure|non remis|no se puede entregar|non recapitabile|unzustellbar", re.I)


def is_bounce(msg) -> bool:
    ctype = (msg.get("Content-Type") or "").lower()
    return ("report-type=delivery-status" in ctype.replace(" ", "")
            or bool(BOUNCE_FROM.search(msg.get("From") or ""))
            or bool(BOUNCE_SUBJECT.search(msg.get("Subject") or "")))


def bounce_reason(raw: str) -> tuple[bool, str]:
    """(hard, reason). Hard = permanent (5.x.x): the address doesn't work."""
    status = re.search(r"Status:\s*([245])\.\d{1,3}\.\d{1,3}", raw)
    diag = re.search(r"Diagnostic-Code:\s*[^;\n]*;\s*([^\n]{0,160})", raw)
    hard = status.group(1) == "5" if status else True
    reason = (diag.group(1).strip() if diag else "delivery failed")[:160]
    return hard, reason


AUTO_SUBJECT = re.compile(r"out of (the )?office|automatic reply|auto.?reply|autoreply|absence|absent|"
                          r"réponse automatique|respuesta autom|risposta automatica|fuera de la oficina|"
                          r"vacaciones|vacances|ferie|urlaub|abwesenheit|nieobecn", re.I)
# The challenge message itself (its wording), not just the word "Mailinblack": stores protected by
# Mailinblack send their REAL replies through it too (header X-Mailinblack, footer).
CHALLENGE = re.compile(r"confirm(er)? (that )?you('re| are) (a )?human|qu.il est bien humain|"
                       r"sender verification|verify (you|your) (are|email)|un clic pour d[ée]livrer|"
                       r"cliquez .{0,40}pour (d[ée]livrer|valider|confirmer)|click .{0,40}to (deliver|release) your", re.I)
CHALLENGE_SENDER = re.compile(r"mailinblack|spamarrest|boxbe|invitations\.", re.I)


def auto_reply_kind(msg, body: str) -> str:
    """'' for a real reply; 'challenge' for anti-spam confirmation requests; 'auto' for out-of-office etc."""
    sender = email.utils.parseaddr(msg.get("From") or "")[1]
    head = (msg.get("Subject") or "") + " " + (body or "")[:800]  # their own words, not the quoted thread below
    if CHALLENGE_SENDER.search(sender.split("@")[-1]) or CHALLENGE.search(head):
        return "challenge"
    auto_hdr = (msg.get("Auto-Submitted") or "").lower()
    if (auto_hdr and auto_hdr != "no") or msg.get("X-Autoreply") or msg.get("X-Autorespond") \
            or (msg.get("Precedence") or "").lower() in ("auto_reply", "bulk", "junk") \
            or AUTO_SUBJECT.search(msg.get("Subject") or ""):
        return "auto"
    return ""


# ---- The order of checks before a send (condensed from send_approved)

def send_decision(r: dict, voice: dict, sent_today: int, limit: int, company_index: dict,
                  tab_name: str = "Stores", now: datetime | None = None) -> tuple[str, str]:
    """('send' | 'wait' | 'hold' | 'skip', why). Nothing is sent unless a person set the row to APPROVED."""
    if r.get("Status") != "APPROVED":
        return "skip", "not approved by a person"
    if sent_today >= limit:
        return "wait", f"daily limit of {limit} reached; it goes tomorrow"
    if not send_address(r):
        return "hold", "no usable address: it must be published on their own site"
    other = already_contacted(r, tab_name, company_index)
    if other and "send anyway" not in (r.get("Analysis Notes") or "").lower():
        return "hold", f"{other['company']} was already contacted ({other['status']} {other['date']})"
    ok, window = in_send_window(r, voice, now)
    if not ok:
        return "wait", f"waits for {window}"
    return "send", ""
