# README — Syllabus → Notion + Google Calendar agent (Composio)

## What this agent does

This Python script automates a common course-management workflow:

1. Downloads a syllabus PDF from **Google Drive** (via Composio Tool Router).
2. Extracts lesson/week text from the PDF.
3. Inserts one row per lesson into a **Notion database** (via Composio Notion toolkit).
4. Schedules corresponding events in **Google Calendar** (via Composio Google Calendar toolkit).

Goal: remove repetitive manual steps (copy/paste from PDF into Notion, create calendar events).

---

## Why this is useful / innovative

* Connects three services (Drive → Notion → Calendar) using **Composio Tool Router** so the agent can run end-to-end without manual copy/paste.
* Shows a reproducible template for many organizational workflows (syllabi, meeting agendas, training plans).
* Uses robust download detection and resilient tool invocation to tolerate small SDK differences.

---

# Quick start (beginner friendly)

## Prerequisites

* Python 3.10+ (or 3.8+ — match your environment)
* A working Composio account and **Composio API key**.
* Composio **auth config IDs** created in the Composio dashboard for:

  * Google Drive toolkit (called `GOOGLE_DRIVE_AUTH_CONFIG_ID`)
  * Notion toolkit (called `NOTION_AUTH_CONFIG_ID`)
  * Google Calendar toolkit (called `GOOGLE_CAL_AUTH_CONFIG_ID`)
* Composio integration connected to your Notion workspace (see **Notion setup** below).
* `syllabus.pdf` uploaded to the Google Drive of the account you will link during the auth flow (script searches for exact file name by default).
* The Python script file (your `run_agent.py`) — you already have it.

> **Important:** The Notion database ID must be a Notion **database** (not a page URL). See step *How to get NOTION_DATABASE_ID* below.

---

## Files you should have (from this project)

* `run_agent.py` — the script you posted (keep it unchanged except for environment).
* `.env` — file storing environment variables (example below).
* `requirements.txt` — packages for the virtualenv (example below).

### Example `requirements.txt`

```
composio>=0.0.0    # your installed composio SDK version (match what's in your venv)
composio-client>=0.0.0
python-dotenv
pymupdf
```

(Replace package version pins with versions you used in your environment. If you installed composio from pip earlier, keep same version.)

---

## .env.example

Create a `.env` (or copy `.env.example`) in the project root with the following keys:

```
COMPOSIO_API_KEY=sk_XXXXXXXXXXXXXXXXXXXXXXXX
GOOGLE_DRIVE_AUTH_CONFIG_ID=ac_xxx_google_drive_auth_config
NOTION_AUTH_CONFIG_ID=ac_xxx_notion_auth_config
GOOGLE_CAL_AUTH_CONFIG_ID=ac_xxx_google_calendar_auth_config

# Optional / runtime
COMPOSIO_USER_ID=            # (optional) put a stable user UUID if you want
DOWNLOAD_DIR=./downloads
SYLLABUS_FILE_NAME=syllabus.pdf
NOTION_DATABASE_ID=         # set after creating Notion DB (see below)
CALENDAR_ID=primary
START_DATE=2025-10-06
START_TIME=09:00
TIMEZONE=Asia/Kolkata
CONNECTIONS_FILE=connections.json
```

**Important:** `NOTION_DATABASE_ID` must be the database id (32 hex characters, with or without hyphens). Do **not** set it to an `ac_...` auth config id. See below how to get the correct database id.

---

## How to run locally (step-by-step)

1. Create & activate a virtual environment:

   ```bash
   python -m venv .venv
   source .venv/bin/activate        # macOS / Linux
   .venv\Scripts\activate           # Windows (PowerShell/cmd)
   pip install -r requirements.txt
   ```

2. Create `.env` from `.env.example` and fill your `COMPOSIO_API_KEY` and the `*_AUTH_CONFIG_ID` values (obtained from Composio dashboard). Leave `NOTION_DATABASE_ID` blank for now if you will let the script create the database automatically, or fill it if you already created a database.

3. Upload your `syllabus.pdf` to the Google Drive account you will connect in the script (script searches for the file name exactly; change `SYLLABUS_FILE_NAME` if needed).

4. Run the script:

   ```bash
   python run_agent.py
   ```

5. The script will:

   * Print a browser URL to link your Google Drive / Notion / Calendar account(s) (if not already connected). Open the URL(s) and complete the OAuth flow.
   * Download the syllabus, extract text, create Notion rows, create Calendar events.
   * It will write/maintain `connections.json` (stores the Composio connection ids so you don't need to re-link each run).

---

## Notion setup — exact steps (**crucial**)

Your Notion database must match the properties the script writes. The script inserts rows with two properties:

* `Name` — **title** property (this is the default database title column).
* `Description` — **rich_text** property (script expects property called exactly `Description`).

**Do this in Notion before running (if you don't want the script to create the DB):**

1. Create a new **Database** (e.g., a table view) under any parent page you own — call it e.g., `Course Syllabus`.
2. Ensure the database has:

   * A Title column with label **Name** (default).
   * A **Description** column (property type: *Text* / *Rich Text*). If it's named differently (e.g., `Topic`), either rename it to `Description` or change `create_notion_row()` in the script to match the property name.
3. **Important: share** the parent page (or the database itself) with your **Composio Notion integration** — this gives the integration permission to insert rows:

   * In Notion share dialog, invite the integration/bot (the integration will appear by the name you gave it in Composio Notion auth config).
   * If you do not share the database with the integration, inserts will fail with 404 / validation errors.

### How to get the Notion database id (for NOTION_DATABASE_ID)

* Open the database in Notion (table view).
* Look at the URL — the database id is the 32-character hex token in the URL. It may appear with hyphens or without.

  * Example URL: `https://www.notion.so/yourworkspace/28cdc4bd448c80a995a7df1f22d0833d?v=...`
  * The database id is the `28cdc4bd448c80a995a7df1f22d0833d` portion (32 hex chars).
* Set `NOTION_DATABASE_ID` to that 32-char id (you may include hyphens if present — the script will pass the string through to Composio).

> If the script attempts to create a database automatically, it will try to use the Composio toolkit for creating DBs. Many people prefer to create the DB manually in Notion and then set `NOTION_DATABASE_ID` to be safe.

---

## How to connect third-party tools using Composio Tool Router (in brief)

1. In the Composio dashboard, add the toolkit (Notion / Google Drive / Google Calendar).
2. Create an **Auth Config** for each toolkit. Copy the `ac_...` auth_config_id into `.env` variables `*_AUTH_CONFIG_ID`.
3. Run `run_agent.py`. The script uses `composio.connected_accounts.link(...)` to initiate the per-user OAuth flow (it prints a redirect URL). Open that URL and sign in with the account to give the Composio integration access.

   * After linking completes, the script waits for the connection to finish and saves results to `connections.json`.
4. Once linked, the script uses Composio `tools.execute(...)` calls to run toolkit actions under that user.

---

## What to check if things fail

* **Tool slug errors / NotFoundError**: ensure the tool slug used by the script (e.g., `NOTION_INSERT_ROW_DATABASE`) exists for your Composio account. Tool slugs are case-sensitive.
* **Notion validation errors** like `"Topic is not a property that exists."` — means your Notion DB property names/types don't match what the script sends. Fix either Notion DB column names or modify `create_notion_row()` to send the correct property name.
* **Database ID problems**: If you pass an auth config id (`ac_...`) into `NOTION_DATABASE_ID` by mistake you will get validation errors. Use the Notion database id (32 chars).
* **Permissions**: The Notion integration must be shared with the database or its parent page.
* **Downloaded PDF not found**: script searches `DOWNLOAD_DIR` — check the printed path and that file exists.
* **Composio API key missing or invalid** — verify `COMPOSIO_API_KEY` in `.env`.

---

## Minimal troubleshooting checklist (quick)

1. Did you upload `syllabus.pdf` to the Drive account you linked? ✔
2. Did you complete the link flow shown by the script (open printed URL and sign in)? ✔
3. Is `NOTION_DATABASE_ID` a 32-char uuid from Notion URL (not `ac_...`)? ✔
4. Is your Notion database shared with Composio integration (invite the integration/bot)? ✔
5. Does the DB have `Name` (title) and `Description` (rich_text) properties? ✔

---
## Team Members (Pixar)

- Philip Winston Samuel
- Paul Samuel W E (LEADER)
- Subhiselvam A B
