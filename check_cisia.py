import hashlib
import html
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

URL = "https://testcisia.it/calendario.php?tolc=cents&l=gb&lingua=inglese"
STATE_FILE = Path("cisia_state.json")

TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "").strip()
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "").strip()

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 14; Mobile) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Mobile Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
}


def send_telegram(text: str) -> None:
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("Не заданы TG_BOT_TOKEN или TG_CHAT_ID")
        return
    api_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    payload = urllib.parse.urlencode({
        "chat_id": TG_CHAT_ID,
        "text": text,
    }).encode("utf-8")
    req = urllib.request.Request(api_url, data=payload, method="POST")
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def strip_tags(s: str) -> str:
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def parse_rows(raw_html: str) -> list[dict]:
    rows = []
    for tr in re.findall(r"<tr\b[^>]*>(.*?)</tr>", raw_html, flags=re.S | re.I):
        cells = [
            strip_tags(td)
            for td in re.findall(r"<t[dh]\b[^>]*>(.*?)</t[dh]>", tr, flags=re.S | re.I)
        ]
        cells = [c for c in cells if c]
        joined = " | ".join(cells)
        if not joined:
            continue
        if re.search(
            r"\b(CENT@UNI|CENT@HOME|CEnT-S|AVAILABLE SEATS|BOOKINGS CLOSED|NOT LONGER AVAILABLE)\b",
            joined,
            flags=re.I,
        ):
            row_id = hashlib.md5(joined.encode("utf-8")).hexdigest()[:10]
            rows.append({
                "id": row_id,
                "cells": cells,
                "text": joined,
                "is_available": bool(re.search(r"AVAILABLE SEATS", joined, flags=re.I)),
            })
    return rows


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"rows": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    state = load_state()
    prev_texts = {r["text"] for r in state.get("rows", [])}
    prev_avail = {r["text"] for r in state.get("rows", []) if r.get("is_available")}

    req = urllib.request.Request(URL, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=25) as resp:
        raw_html = resp.read().decode("utf-8", errors="ignore")

    new_rows = parse_rows(raw_html)
    now_str = datetime.utcnow().strftime("%d.%m.%Y %H:%M UTC")
    events = []

    for r in new_rows:
        txt = r["text"]
        if prev_texts and txt not in prev_texts:
            events.append(f"🆕 Новая дата:\n{txt}")
        elif r["is_available"] and txt not in prev_avail:
            events.append(f"✅ Появились места:\n{txt}")

    if events:
        msg = f"🔔 CISIA CEnT-S ({now_str})\n\n" + "\n\n".join(events[:8])
        send_telegram(msg)

    state["rows"] = new_rows
    state["last_check"] = now_str
    save_state(state)
    print(f"Проверка завершена. Найдено строк: {len(new_rows)}, новых событий: {len(events)}")


if __name__ == "__main__":
    main()
  
