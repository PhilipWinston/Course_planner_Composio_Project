# Friction Log (challenges encountered & how to overcome)

This documents the issues I saw while building and running this agent and how to fix them or work around them — useful for judges and maintainers.

## 1) Tool slug mismatch / NotFoundError

**Symptom:** `NotFoundError: Tool NOTION_INSERT_ROW not found` or `Tool Create Notion Database not found`.

**Cause:** The SDK code used the wrong tool slug. Composio tool names may differ across versions (e.g., `NOTION_INSERT_ROW` vs `NOTION_INSERT_ROW_DATABASE`).

**Fix / Mitigation:**

* Inspect Composio toolkit docs or the toolkit listing in the dashboard to confirm available slug names.
* Update script to call the correct slug (`NOTION_INSERT_ROW_DATABASE` used here).
* Added a `ComposioWrapper.execute_tool` that tries several call signatures to tolerate different SDK wrappers.

## 2) Notion database vs auth config confusion

**Symptom:** Validation error: `body.parent.database_id should be a valid uuid, instead was "ac_..."` or similar.

**Cause:** Passing the Composio auth config id (`ac_...`) as `NOTION_DATABASE_ID` by mistake. The auth config id is **not** the database id.

**Fix:**

* Obtain the Notion database id from the Notion URL (32 hex characters) and set `NOTION_DATABASE_ID`.
* If letting the script create the database, ensure Composio toolkit has a `create database` tool slug available. Many teams prefer manual DB creation to avoid toolkit differences.

## 3) Notion property name/type mismatches

**Symptom:** `Topic is not a property that exists.` or `Input should be 'title'|'rich_text'|...`

**Cause:** The script was inserting a property named `Topic` while your DB used `Description`, or property type mismatched.

**Fix:**

* Update your Notion database columns to match exactly the names used by the script, or change the script to use the actual property names.
* Property names are **case sensitive** for Composio/Notion validation.

## 4) Downloaded file path detection

**Symptom:** `Could not locate the downloaded PDF on disk` even though response shows a path.

**Cause:** Different SDK responses for file downloads: `file_path`, `path`, `download_path`, sometimes nested in lists or a `body` field. The Composio SDK or client might return different structures depending on versions.

**Fixes added to script:**

* Recursive search in `DOWNLOAD_DIR` for `.pdf`.
* Scans nested dicts for keys ending with `.pdf`.
* Writes `body` content to file if provided.

## 5) Composio client method signature differences

**Symptom:** `Tools.execute() got an unexpected keyword argument 'tool_slug'` or `unexpected keyword argument 'tool_slug'`.

**Cause:** Different client versions accept different argument names/positions.

**Mitigation implemented:**

* `ComposioWrapper.execute_tool` attempts several invocation forms (positional and keyword) and returns normalized results. This reduces breakage between client versions.

## 6) Notion DB creation missing tool slug

**Symptom:** `Tool Create Notion Database not found`.

**Cause:** The toolkit available to your Composio instance may not include the DB creation tool or the slug name is different.

**Workaround:**

* Create the database manually in Notion (recommended) and set `NOTION_DATABASE_ID` in `.env` to avoid relying on toolkit DB creation.
* If you need the script to create DBs, check the exact tool slug in the Composio dashboard and replace `create_notion_database` calls accordingly.

## 7) Authentication/linking/permissions issues

**Symptom:** 404 errors or permission denied when inserting rows.

**Cause:** Integration not shared with the database or wrong user linked.

**Fix:**

* Share the parent page / DB with the Composio integration (in Notion's Share modal).
* Ensure you complete the OAuth link flow printed by the script (open the URL it prints and accept permissions).

---


