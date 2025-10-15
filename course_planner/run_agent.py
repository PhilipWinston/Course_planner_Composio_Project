#!/usr/bin/env python3
"""
Updated run_agent.py — improved download detection (recursive search)
Drop-in replacement: copy this over your existing run_agent.py
"""

import os
import sys
import time
import json
import uuid
import re
import datetime
import traceback
from dotenv import load_dotenv

# PDF parsing
import fitz  # PyMuPDF

# Composio SDK
from composio import Composio

load_dotenv()

# ---------- Environment / Config ----------
COMPOSIO_API_KEY = os.getenv("COMPOSIO_API_KEY")
GOOGLE_DRIVE_AUTH_CONFIG_ID = os.getenv("GOOGLE_DRIVE_AUTH_CONFIG_ID")
NOTION_AUTH_CONFIG_ID = os.getenv("NOTION_AUTH_CONFIG_ID")
GOOGLE_CAL_AUTH_CONFIG_ID = os.getenv("GOOGLE_CAL_AUTH_CONFIG_ID")

CONNECTIONS_FILE = os.getenv("CONNECTIONS_FILE", "connections.json")
COMPOSIO_USER_ID_ENV = os.getenv("COMPOSIO_USER_ID")  # optional pre-set
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")

SYLLABUS_FILE_NAME = os.getenv("SYLLABUS_FILE_NAME", "syllabus.pdf")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")
START_DATE = os.getenv("START_DATE")  # YYYY-MM-DD
START_TIME = os.getenv("START_TIME", "09:00")
TIMEZONE = os.getenv("TIMEZONE", "UTC")

# Tool slugs
FIND_FILE_SLUG = "GOOGLEDRIVE_FIND_FILE"
DOWNLOAD_FILE_SLUG = "GOOGLEDRIVE_DOWNLOAD_FILE"
NOTION_INSERT_ROW_SLUG = "NOTION_INSERT_ROW_DATABASE"
CALENDAR_CREATE_EVENT_SLUG = "GOOGLECALENDAR_CREATE_EVENT"

MAX_LESSONS = 12
SLEEP_BETWEEN_CALLS = 0.35

# ---------- Helpers ----------
def info(msg): print("[INFO]", msg)
def error(msg): print("[ERROR]", msg)
def save_json(path, obj):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, default=str)
def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def ensure_dir(path):
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)

# ---------- Composio wrapper with robust execute ----------
class ComposioWrapper:
    def __init__(self, api_key: str, user_id: str = None, download_dir: str = None):
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        if download_dir:
            kwargs["file_download_dir"] = download_dir
        self.client = Composio(**kwargs)
        self.user_id = user_id

    def set_user(self, user_id: str):
        self.user_id = user_id

    def execute_tool(self, tool_slug: str, arguments: dict):
        """
        Try several invocation signatures for composio.tools.execute(...) and normalize result.
        """
        attempts = []
        forms = [
            lambda: self.client.tools.execute(slug=tool_slug, user_id=self.user_id, arguments=arguments),
            lambda: self.client.tools.execute(slug=tool_slug, arguments=arguments, user_id=self.user_id),
            lambda: self.client.tools.execute(tool_slug, self.user_id, arguments),
            lambda: self.client.tools.execute(tool_slug, arguments, self.user_id),
            lambda: self.client.tools.execute(self.user_id, tool_slug, arguments),
            lambda: self.client.tools.execute(slug=tool_slug, args=arguments, user_id=self.user_id),
        ]
        last_exc = None
        for f in forms:
            try:
                resp = f()
                if isinstance(resp, dict):
                    ok = resp.get("successful", True)
                    data = resp.get("data", resp)
                    err = resp.get("error")
                    return {"ok": ok, "data": data, "error": err}
                else:
                    ok = getattr(resp, "successful", True)
                    data = getattr(resp, "data", None) or resp
                    err = getattr(resp, "error", None)
                    return {"ok": ok, "data": data, "error": err}
            except TypeError as te:
                last_exc = te
                attempts.append(("TypeError", str(te)))
                continue
            except Exception as e:
                tb = traceback.format_exc()
                return {"ok": False, "data": None, "error": f"{e}\n{tb}"}
        return {"ok": False, "data": None, "error": f"All execute attempts failed. Last TypeError: {last_exc}; attempts: {attempts}"}

# ---------- Linking helpers ----------
def link_tool_and_wait(composio_client: Composio, user_id: str, auth_config_id: str, friendly_name: str, timeout_seconds: int = 300):
    info(f"Starting link flow for {friendly_name} (auth_config_id={auth_config_id})")
    try:
        connection_request = composio_client.connected_accounts.link(user_id=user_id, auth_config_id=auth_config_id, callback_url="https://www.google.com")
    except Exception as e:
        tb = traceback.format_exc()
        raise RuntimeError(f"Failed to start link flow for {friendly_name}: {e}\n{tb}")

    redirect_url = getattr(connection_request, "redirect_url", None) or connection_request.get("redirect_url", None)
    if redirect_url:
        print("\n--- OPEN THIS URL IN YOUR BROWSER ---\n")
        print(redirect_url)
        print("\n--- AFTER SIGN IN, RETURN HERE ---\n")
    else:
        info("No redirect URL returned by SDK — complete auth via Composio dashboard if needed.")

    try:
        connected = connection_request.wait_for_connection(timeout=timeout_seconds)
        info(f"{friendly_name} linked.")
        return connected
    except Exception as e:
        tb = traceback.format_exc()
        raise RuntimeError(f"Error waiting for connection for {friendly_name}: {e}\n{tb}")

# ---------- PDF / parsing ----------
def extract_text_from_pdf(path: str) -> str:
    info(f"Extracting text from PDF: {path}")
    doc = fitz.open(path)
    texts = []
    for p in doc:
        texts.append(p.get_text())
    return "\n".join(texts)

def parse_lessons(text: str, max_lessons: int = MAX_LESSONS):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    lessons = []
    i = 0
    while i < len(lines):
        m = re.match(r'^(Week\s*\d+)\s*[:\-]?\s*(.*)', lines[i], re.I)
        if m:
            header = m.group(1)
            rem = m.group(2).strip()
            desc_parts = []
            if rem:
                desc_parts.append(rem)
            j = i + 1
            while j < len(lines) and not re.match(r'^(Week\s*\d+)', lines[j], re.I):
                desc_parts.append(lines[j])
                j += 1
            lessons.append((header, " ".join(desc_parts).strip()))
            i = j
        else:
            i += 1
    if not lessons:
        words = text.split()
        total = len(words)
        if total == 0:
            return []
        chunk = max(total // max_lessons, 1)
        for k in range(max_lessons):
            start = k * chunk
            end = start + chunk if k < max_lessons - 1 else total
            lessons.append((f"Week {k+1}", " ".join(words[start:end])))
    return lessons[:max_lessons]

# ---------- Notion & Calendar helpers ----------
# ---------- Notion helper ----------
def create_notion_row(wrapper, database_id, title, content):
    props = [
        {"name": "Name", "type": "title", "value": title},
        {"name": "Description", "type": "rich_text", "value": content}  # match the Notion property
    ]
    return wrapper.execute_tool("NOTION_INSERT_ROW_DATABASE", {
        "database_id": database_id,
        "properties": props
    })
# ---------- Calendar helper ----------

def create_calendar_event(wrapper: ComposioWrapper, calendar_id: str, start_iso: str, timezone: str, summary: str, description: str):
    args = {
        "calendar_id": calendar_id,
        "start_datetime": start_iso,
        "timezone": timezone,
        "summary": summary,
        "description": description,
        "event_duration_hour": 1
    }
    return wrapper.execute_tool(CALENDAR_CREATE_EVENT_SLUG, args)

# ---------- Main ----------
def main():
    if not COMPOSIO_API_KEY:
        error("COMPOSIO_API_KEY missing in environment (.env).")
        sys.exit(1)

    ensure_dir(DOWNLOAD_DIR)

    # load or create connections file
    connections = {}
    if os.path.exists(CONNECTIONS_FILE):
        try:
            connections = load_json(CONNECTIONS_FILE)
            info(f"Loaded connections from {CONNECTIONS_FILE}")
        except Exception:
            info("Could not parse existing connections file — will recreate.")
            connections = {}

    user_id = connections.get("user_id") or COMPOSIO_USER_ID_ENV or str(uuid.uuid4())
    info(f"Using user_id: {user_id}")

    composio_raw = Composio(api_key=COMPOSIO_API_KEY)

    # Link if needed
    connections.setdefault("connections", {})
    try:
        if "google_drive" not in connections["connections"] and GOOGLE_DRIVE_AUTH_CONFIG_ID:
            conn = link_tool_and_wait(composio_raw, user_id, GOOGLE_DRIVE_AUTH_CONFIG_ID, "Google Drive")
            connections["connections"]["google_drive"] = conn
            save_json(CONNECTIONS_FILE, {"user_id": user_id, "connections": connections["connections"]})
        else:
            info("Google Drive connection exists or GOOGLE_DRIVE_AUTH_CONFIG_ID not provided.")

        if "notion" not in connections["connections"] and NOTION_AUTH_CONFIG_ID:
            conn = link_tool_and_wait(composio_raw, user_id, NOTION_AUTH_CONFIG_ID, "Notion")
            connections["connections"]["notion"] = conn
            save_json(CONNECTIONS_FILE, {"user_id": user_id, "connections": connections["connections"]})
        else:
            info("Notion connection exists or NOTION_AUTH_CONFIG_ID not provided.")

        if "google_calendar" not in connections["connections"] and GOOGLE_CAL_AUTH_CONFIG_ID:
            conn = link_tool_and_wait(composio_raw, user_id, GOOGLE_CAL_AUTH_CONFIG_ID, "Google Calendar")
            connections["connections"]["google_calendar"] = conn
            save_json(CONNECTIONS_FILE, {"user_id": user_id, "connections": connections["connections"]})
        else:
            info("Google Calendar connection exists or GOOGLE_CAL_AUTH_CONFIG_ID not provided.")
    except Exception as e:
        error(f"Auth/linking flow error: {e}")
        sys.exit(1)

    save_json(CONNECTIONS_FILE, {"user_id": user_id, "connections": connections["connections"]})
    info(f"Connections saved to {CONNECTIONS_FILE}")

    wrapper = ComposioWrapper(api_key=COMPOSIO_API_KEY, user_id=user_id, download_dir=DOWNLOAD_DIR)

    # FIND file in Drive
    info(f"Searching Drive for file named exactly '{SYLLABUS_FILE_NAME}'...")
    find_resp = wrapper.execute_tool(FIND_FILE_SLUG, {"q": f"name = '{SYLLABUS_FILE_NAME}'"})
    if not find_resp["ok"]:
        error("Drive find failed: " + str(find_resp["error"]))
        sys.exit(1)
    data = find_resp["data"] or {}
    files = None
    if isinstance(data, dict):
        files = data.get("files") or data.get("items") or []
    elif isinstance(data, list):
        files = data
    else:
        files = []
    if not files:
        error(f"No file named '{SYLLABUS_FILE_NAME}' found in Drive for user {user_id}.")
        sys.exit(1)
    file_meta = files[0]
    file_id = file_meta.get("id") or file_meta.get("file_id") or file_meta.get("driveId")
    info(f"Found Drive file id: {file_id}")

    time.sleep(SLEEP_BETWEEN_CALLS)

    # DOWNLOAD file
    info("Downloading file via Composio...")
    dl_resp = wrapper.execute_tool(DOWNLOAD_FILE_SLUG, {"file_id": file_id})
    if not dl_resp["ok"]:
        error("Drive download failed: " + str(dl_resp["error"]))
        sys.exit(1)
    dl_data = dl_resp["data"] or {}

    # --------------- Robust local path resolution ---------------
    local_path = None

    # 1) Common response keys
    for key in ("file_path", "path", "local_path", "download_path", "file", "name"):
        val = dl_data.get(key) if isinstance(dl_data, dict) else None
        if val:
            # if it's just a name, build path
            candidate = val if os.path.isabs(val) else os.path.join(DOWNLOAD_DIR, val)
            if os.path.exists(candidate):
                local_path = os.path.abspath(candidate)
                break
            # also accept if val itself is a valid absolute path
            if os.path.exists(val):
                local_path = os.path.abspath(val)
                break

    # 2) If not found, check nested dicts (some SDKs return {'files':[{'file_path': ...}]})
    if not local_path:
        def search_dict_for_path(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, str) and v.lower().endswith(".pdf") and (os.path.exists(v) or os.path.exists(os.path.join(DOWNLOAD_DIR, v))):
                        candidate = v if os.path.isabs(v) else os.path.join(DOWNLOAD_DIR, v)
                        if os.path.exists(candidate):
                            return os.path.abspath(candidate)
                    elif isinstance(v, dict) or isinstance(v, list):
                        found = search_dict_for_path(v)
                        if found:
                            return found
            elif isinstance(obj, list):
                for item in obj:
                    found = search_dict_for_path(item)
                    if found:
                        return found
            return None
        local_path = search_dict_for_path(dl_data)

    # 3) If still not found, recursively search DOWNLOAD_DIR for the exact filename
    if not local_path:
        info(f"Looking recursively under {DOWNLOAD_DIR} for '{SYLLABUS_FILE_NAME}' or any PDF...")
        for root, dirs, files_in_dir in os.walk(DOWNLOAD_DIR):
            for fname in files_in_dir:
                if fname == SYLLABUS_FILE_NAME or fname.lower().endswith(".pdf"):
                    candidate = os.path.join(root, fname)
                    # prefer exact filename match, otherwise accept first pdf
                    if fname == SYLLABUS_FILE_NAME:
                        local_path = os.path.abspath(candidate)
                        break
                    if not local_path:
                        local_path = os.path.abspath(candidate)
            if local_path:
                break

    # 4) If dl_data contains a 'body' (bytes/text), write to file
    if not local_path and isinstance(dl_data, dict) and dl_data.get("body"):
        body = dl_data.get("body")
        outp = os.path.join(DOWNLOAD_DIR, SYLLABUS_FILE_NAME)
        mode = "wb" if isinstance(body, (bytes, bytearray)) else "w"
        with open(outp, mode) as fh:
            fh.write(body)
        local_path = os.path.abspath(outp)

    if not local_path or not os.path.exists(local_path):
        error("Could not locate the downloaded PDF on disk. Here is the raw download response data for inspection:")
        print(json.dumps(dl_data, default=str, indent=2)[:4000])  # print truncated to avoid spamming
        sys.exit(1)

    info(f"Syllabus downloaded to: {local_path}")
    time.sleep(SLEEP_BETWEEN_CALLS)

    # Extract text and parse lessons
    try:
        text = extract_text_from_pdf(local_path)
    except Exception as e:
        error(f"Failed to parse PDF: {e}")
        sys.exit(1)

    lessons = parse_lessons(text, max_lessons=MAX_LESSONS)
    if not lessons:
        error("No lessons parsed from PDF.")
        sys.exit(1)
    info(f"Parsed {len(lessons)} lessons.")

    # Create Notion rows
    if NOTION_DATABASE_ID:
        info("Creating Notion rows...")
        for (title, desc) in lessons:
            info(f" -> Notion row: {title}")
            nres = create_notion_row(wrapper, NOTION_DATABASE_ID, title, desc)
            if not nres["ok"]:
                error(f"Notion create failed: {nres['error']}")
            else:
                info("   Notion row created.")
            time.sleep(SLEEP_BETWEEN_CALLS)
    else:
        info("NOTION_DATABASE_ID not set; skipping Notion creation.")

    # Schedule Calendar events
    if START_DATE:
        try:
            dt0 = datetime.datetime.fromisoformat(START_DATE)
        except Exception:
            dt0 = datetime.datetime.strptime(START_DATE, "%Y-%m-%d")
    else:
        dt0 = datetime.datetime.now()
    hh, mm = [int(x) for x in START_TIME.split(":")]
    dt0 = dt0.replace(hour=hh, minute=mm, second=0, microsecond=0)

    info("Creating calendar events...")
    for i, (title, desc) in enumerate(lessons):
        event_dt = dt0 + datetime.timedelta(weeks=i)
        start_iso = event_dt.isoformat()
        info(f" -> Scheduling '{title}' at {start_iso} ({TIMEZONE})")
        cresp = create_calendar_event(wrapper, CALENDAR_ID, start_iso, TIMEZONE, title, desc)
        if not cresp["ok"]:
            error(f"Calendar create failed: {cresp['error']}")
        else:
            info("   Event created.")
        time.sleep(SLEEP_BETWEEN_CALLS)

    info("Done. Check Notion and Google Calendar for results.")
    save_json(CONNECTIONS_FILE, {"user_id": user_id, "connections": connections["connections"]})

if __name__ == "__main__":
    main()
