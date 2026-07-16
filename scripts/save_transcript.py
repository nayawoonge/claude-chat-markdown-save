#!/usr/bin/env python3
"""
Claude Chat Logger — Stop-hook transcript-to-markdown converter.

Reads the Stop-hook JSON payload from stdin, locates the session's JSONL
transcript, and APPENDS any new turns to a single per-session Markdown file.

The log is grow-only: whatever is already saved is kept verbatim and only
turns not yet present are added (matched by a hidden per-turn id marker). So a
turn is never lost even if the source transcript later drops it — e.g. after
context compaction — and nothing scrolls away when the chat view truncates.

The transcript JSONL format is internal to Claude Code and can change between
releases, so every field access here is defensive: unknown line types are
skipped, missing keys fall back to sensible defaults, and the script never
raises into the hook runner (any error is swallowed so it can't block Claude).

Configuration (all optional, via environment variables):
  CLAUDE_LOG_DIR                Output directory (default: ~/claude-logs)
  CLAUDE_LOG_INCLUDE_THINKING   "1" to include the model's thinking blocks (default: 0)
  CLAUDE_LOG_INCLUDE_TOOLS      "0" to omit tool calls/results (default: 1)
  CLAUDE_LOG_MAX_TOOL_CHARS     Truncate tool input/output to N chars (default: 1500)
"""

import hashlib
import json
import os
import re
import sys
from datetime import datetime

# ----------------------------------------------------------------------------
# Config
# ----------------------------------------------------------------------------

def _env_flag(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


LOG_DIR = os.path.expanduser(os.environ.get("CLAUDE_LOG_DIR", "~/claude-logs"))
INCLUDE_THINKING = _env_flag("CLAUDE_LOG_INCLUDE_THINKING", False)
INCLUDE_TOOLS = _env_flag("CLAUDE_LOG_INCLUDE_TOOLS", True)
try:
    MAX_TOOL_CHARS = int(os.environ.get("CLAUDE_LOG_MAX_TOOL_CHARS", "1500"))
except ValueError:
    MAX_TOOL_CHARS = 1500


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def _slugify(text: str, max_len: int = 60) -> str:
    text = (text or "").strip().lower()
    # keep unicode word chars (so Korean/other scripts survive), collapse the rest
    text = re.sub(r"[\s/\\]+", "-", text)
    text = re.sub(r"[^\w\-]", "", text, flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text[:max_len] or "session"


def _fmt_ts(ts: str) -> str:
    """Turn an ISO-8601 timestamp into a compact local-ish display string."""
    if not ts:
        return ""
    try:
        s = ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts


def _truncate(text: str, limit: int) -> str:
    if limit and len(text) > limit:
        return text[:limit] + f"\n… [truncated, {len(text) - limit} more chars]"
    return text


def _content_to_text(content) -> str:
    """Flatten a tool_result-style content value into plain text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    parts.append(b.get("text", ""))
                elif "text" in b:
                    parts.append(str(b.get("text", "")))
                else:
                    parts.append(json.dumps(b, ensure_ascii=False))
            else:
                parts.append(str(b))
        return "\n".join(p for p in parts if p)
    if content is None:
        return ""
    return str(content)


SESSION_MARKER = "<!-- claude-session: {sid} -->"


def _file_session_id(path: str):
    """Read the session-id marker from an existing log file, if present."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            first = fh.readline()
    except Exception:
        return None
    m = re.match(r"<!--\s*claude-session:\s*(.+?)\s*-->", first)
    return m.group(1) if m else None


def _find_session_file(log_dir: str, session_id: str):
    """Return the path of the existing log file for this session, or None.

    Files are matched by the embedded session-id marker, not by name — so a
    session's file is found again even after its title (and thus filename)
    changed on a previous run.
    """
    try:
        names = os.listdir(log_dir)
    except Exception:
        return None
    for name in names:
        if not name.endswith(".md"):
            continue
        path = os.path.join(log_dir, name)
        if _file_session_id(path) == session_id:
            return path
    return None


def _resolve_output_path(log_dir, session_id, disp_title):
    """Decide the file to write, reusing/renaming this session's file.

    - Filename is derived from the session title (clean, no date/id noise).
    - If this session already has a file (found via its marker), and the title
      changed, the existing file is RENAMED rather than a new one created.
    - If a *different* session already owns the desired name, a short session
      id is appended to avoid clobbering it.
    """
    base = _slugify(disp_title, 60)
    short_sid = session_id.split("-")[0][:8]

    existing = _find_session_file(log_dir, session_id)

    def _claim(candidate):
        """Is `candidate` free for us (missing, or already ours)?"""
        path = os.path.join(log_dir, candidate)
        if not os.path.exists(path):
            return path
        owner = _file_session_id(path)
        if owner == session_id:
            return path
        return None

    target = _claim(base + ".md") or _claim(f"{base}-{short_sid}.md")
    if target is None:
        # Extremely unlikely: fall back to a fully-qualified unique name.
        target = os.path.join(log_dir, f"{base}-{session_id}.md")

    # If we already had a file under a different (old-title) name, move it.
    if existing and os.path.abspath(existing) != os.path.abspath(target):
        try:
            os.replace(existing, target)
        except Exception:
            # If the rename fails, just write to the new target; the old file
            # stays behind but the session content is never lost.
            pass

    return target


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------

TURN_MARKER_RE = re.compile(r"<!--\s*turn:\s*(.+?)\s*-->")
HEADER_SEP = "\n---\n"


def _compute_title(entries):
    """The session's display title: prefer the model title, else first user msg."""
    ai_title = None
    for o in entries:
        if isinstance(o, dict) and o.get("type") == "ai-title":
            t = o.get("aiTitle") or o.get("title")
            if t:
                ai_title = t
    if ai_title:
        return ai_title
    for o in entries:
        if isinstance(o, dict) and o.get("type") == "user":
            c = (o.get("message") or {}).get("content")
            if isinstance(c, str) and c.strip():
                return c.strip()
            if isinstance(c, list):
                txt = "\n".join(
                    b.get("text", "") for b in c
                    if isinstance(b, dict) and b.get("type") == "text"
                ).strip()
                if txt:
                    return txt
    return None


def _entry_id(o):
    """A stable per-entry id used to deduplicate already-written turns."""
    uid = o.get("uuid")
    if uid:
        return str(uid)
    # Fall back to a content hash so re-runs don't duplicate the same turn.
    try:
        blob = json.dumps(o.get("message", o), ensure_ascii=False, sort_keys=True)
    except Exception:
        blob = str(o)
    return "h" + hashlib.sha1(blob.encode("utf-8", "replace")).hexdigest()[:16]


def _render_entry_body(o):
    """Render one transcript entry to a Markdown block (without the id marker).

    Returns None for entries that produce no visible content.
    """
    etype = o.get("type")
    ts = o.get("timestamp")

    if etype == "user":
        content = (o.get("message") or {}).get("content")
        parts = []
        if isinstance(content, str):
            if content.strip():
                parts.append(f"### 🧑 User · {_fmt_ts(ts)}\n\n{content.strip()}")
        elif isinstance(content, list):
            user_texts, tool_results = [], []
            for b in content:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    user_texts.append(b.get("text", ""))
                elif b.get("type") == "tool_result":
                    tool_results.append(b)
            joined = "\n".join(t for t in user_texts if t).strip()
            if joined:
                parts.append(f"### 🧑 User · {_fmt_ts(ts)}\n\n{joined}")
            if INCLUDE_TOOLS:
                for tr in tool_results:
                    out = _truncate(_content_to_text(tr.get("content")), MAX_TOOL_CHARS).strip()
                    if out:
                        parts.append(
                            "<details>\n<summary>🔧 tool result</summary>\n\n"
                            f"```\n{out}\n```\n\n</details>"
                        )
        return "\n\n".join(parts) if parts else None

    if etype == "assistant":
        content = (o.get("message") or {}).get("content")
        blocks = content if isinstance(content, list) else [content]
        rendered = []
        for b in blocks:
            if isinstance(b, str):
                if b.strip():
                    rendered.append(b.strip())
                continue
            if not isinstance(b, dict):
                continue
            bt = b.get("type")
            if bt == "text":
                t = b.get("text", "").strip()
                if t:
                    rendered.append(t)
            elif bt == "thinking" and INCLUDE_THINKING:
                think = (b.get("thinking") or "").strip()
                if think:
                    rendered.append(
                        "<details>\n<summary>💭 thinking</summary>\n\n"
                        f"{think}\n\n</details>"
                    )
            elif bt == "tool_use" and INCLUDE_TOOLS:
                name = b.get("name", "tool")
                try:
                    pretty = json.dumps(b.get("input", {}), ensure_ascii=False, indent=2)
                except Exception:
                    pretty = str(b.get("input", {}))
                pretty = _truncate(pretty, MAX_TOOL_CHARS)
                rendered.append(
                    f"<details>\n<summary>🔧 tool call · <code>{name}</code></summary>\n\n"
                    f"```json\n{pretty}\n```\n\n</details>"
                )
        if rendered:
            return f"### 🤖 Claude · {_fmt_ts(ts)}\n\n" + "\n\n".join(rendered)
    return None


def render_turns(entries):
    """Turn transcript entries into a list of {id, md} blocks + metadata.

    Each block carries a hidden `<!-- turn: id -->` marker so the appender can
    tell which turns are already in the file and only add new ones.
    """
    turns = []
    first_ts = None
    last_ts = None
    for o in entries:
        if not isinstance(o, dict) or o.get("type") not in ("user", "assistant"):
            continue
        ts = o.get("timestamp")
        if ts:
            first_ts = first_ts or ts
            last_ts = ts
        block = _render_entry_body(o)
        if not block:
            continue
        tid = _entry_id(o)
        turns.append({"id": tid, "md": f"<!-- turn: {tid} -->\n{block}\n"})
    return turns, first_ts, last_ts


def build_header(session_id, disp_title, cwd, first_ts, last_ts):
    lines = [
        f"<!-- claude-session: {session_id} -->",
        f"# {disp_title}",
        "",
        f"- **Session:** `{session_id}`",
        f"- **Directory:** `{cwd or 'unknown'}`",
        f"- **Started:** {_fmt_ts(first_ts) or 'unknown'}",
        f"- **Last updated:** {_fmt_ts(last_ts) or 'unknown'}",
        "",
        "> Auto-saved by [claude-chat-logger](https://github.com/) — new turns are",
        "> **appended** on every stop and existing ones are never rewritten, so the",
        "> full session is preserved even if the chat view (or context) is truncated.",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def _split_existing(text):
    """Split an existing log file into (body_after_header, set_of_turn_ids)."""
    idx = text.find(HEADER_SEP)
    body = text[idx + len(HEADER_SEP):] if idx != -1 else text
    ids = set(TURN_MARKER_RE.findall(text))
    return body.strip("\n"), ids


def main():
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}

    transcript_path = payload.get("transcript_path", "")
    session_id = payload.get("session_id", "") or "unknown-session"
    cwd = payload.get("cwd", "") or os.getcwd()

    if not transcript_path or not os.path.isfile(transcript_path):
        # Nothing to do; never block the stop event.
        return 0

    entries = []
    try:
        with open(transcript_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    except Exception:
        return 0

    if not entries:
        return 0

    turns, first_ts, last_ts = render_turns(entries)
    if not turns:
        return 0

    title = _compute_title(entries)
    disp_title = (title or "Claude Code session").strip().replace("\n", " ")
    if len(disp_title) > 80:
        disp_title = disp_title[:80] + "…"

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        # One file per session, named after the session title. If the title
        # changed since last stop, this renames the existing file instead of
        # creating a new one.
        out_path = _resolve_output_path(LOG_DIR, session_id, disp_title)

        # Grow-only append: keep whatever is already saved verbatim and add
        # only turns not yet present. This means a turn is never lost even if
        # the source transcript later drops it (e.g. after context compaction).
        old_body, existing_ids = "", set()
        if os.path.exists(out_path):
            try:
                old_body, existing_ids = _split_existing(
                    open(out_path, encoding="utf-8").read()
                )
            except Exception:
                old_body, existing_ids = "", set()

        new_blocks = [t["md"] for t in turns if t["id"] not in existing_ids]
        if not new_blocks and old_body:
            # Nothing new to add, but the title may have changed — the rename in
            # _resolve_output_path already handled that, so we can stop here.
            return 0

        # Started time: keep the earliest we can see. If we're extending an
        # existing file we don't have its original start, so fall back to now's
        # first_ts only when there was no prior body.
        body_parts = [p for p in (old_body, "\n\n".join(new_blocks)) if p]
        body = "\n\n".join(body_parts).strip("\n")

        header = build_header(session_id, disp_title, cwd, first_ts, last_ts)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(header + body + "\n")
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Absolutely never propagate an error into the hook runner.
        sys.exit(0)
