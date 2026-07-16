#!/usr/bin/env python3
"""
Claude Chat Logger — Stop-hook transcript-to-markdown converter.

Reads the Stop-hook JSON payload from stdin, locates the session's JSONL
transcript, and (re)writes the WHOLE conversation as a single Markdown file.

Because the file is fully rewritten on every stop, the Markdown log always
holds the complete session — nothing scrolls away or gets lost, even when the
in-editor chat view truncates old messages.

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


def _date_prefix(ts: str) -> str:
    if not ts:
        return "0000-00-00"
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", ts)
        return m.group(1) if m else "0000-00-00"


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


# ----------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------

def render_markdown(entries, session_id, cwd):
    first_ts = None
    last_ts = None
    body = []

    # Prefer the model-generated session title when one exists; fall back to
    # the first user message (filled in during the main pass below).
    title = None
    for o in entries:
        if isinstance(o, dict) and o.get("type") == "ai-title":
            t = o.get("aiTitle") or o.get("title")
            if t:
                title = t
    ai_title_present = title is not None

    for o in entries:
        if not isinstance(o, dict):
            continue
        etype = o.get("type")
        ts = o.get("timestamp")
        if ts:
            first_ts = first_ts or ts
            last_ts = ts

        if etype == "ai-title":
            continue

        if etype == "user":
            msg = o.get("message", {}) or {}
            content = msg.get("content")
            if isinstance(content, str):
                text = content.strip()
                if text:
                    body.append(f"### 🧑 User · {_fmt_ts(ts)}\n\n{text}\n")
                    if not ai_title_present and not title:
                        title = text
            elif isinstance(content, list):
                # A user turn that is a list is usually tool_result output.
                user_texts = []
                tool_results = []
                for b in content:
                    if not isinstance(b, dict):
                        continue
                    bt = b.get("type")
                    if bt == "text":
                        user_texts.append(b.get("text", ""))
                    elif bt == "tool_result":
                        tool_results.append(b)
                joined = "\n".join(t for t in user_texts if t).strip()
                if joined:
                    body.append(f"### 🧑 User · {_fmt_ts(ts)}\n\n{joined}\n")
                    if not ai_title_present and not title:
                        title = joined
                if INCLUDE_TOOLS and tool_results:
                    for tr in tool_results:
                        out = _truncate(_content_to_text(tr.get("content")), MAX_TOOL_CHARS).strip()
                        if out:
                            body.append(
                                "<details>\n<summary>🔧 tool result</summary>\n\n"
                                f"```\n{out}\n```\n\n</details>\n"
                            )

        elif etype == "assistant":
            msg = o.get("message", {}) or {}
            content = msg.get("content")
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
                    tool_input = b.get("input", {})
                    try:
                        pretty = json.dumps(tool_input, ensure_ascii=False, indent=2)
                    except Exception:
                        pretty = str(tool_input)
                    pretty = _truncate(pretty, MAX_TOOL_CHARS)
                    rendered.append(
                        f"<details>\n<summary>🔧 tool call · <code>{name}</code></summary>\n\n"
                        f"```json\n{pretty}\n```\n\n</details>"
                    )
            if rendered:
                body.append(f"### 🤖 Claude · {_fmt_ts(ts)}\n\n" + "\n\n".join(rendered) + "\n")

        # everything else (attachment, queue-operation, last-prompt, mode, …) is skipped

    # ---- assemble document ----
    disp_title = (title or "Claude Code session").strip().replace("\n", " ")
    if len(disp_title) > 80:
        disp_title = disp_title[:80] + "…"

    header = [
        f"# {disp_title}",
        "",
        f"- **Session:** `{session_id}`",
        f"- **Directory:** `{cwd or 'unknown'}`",
        f"- **Started:** {_fmt_ts(first_ts) or 'unknown'}",
        f"- **Last updated:** {_fmt_ts(last_ts) or 'unknown'}",
        "",
        "> Auto-saved by [claude-chat-logger](https://github.com/) — the full session is",
        "> rewritten on every stop, so nothing is lost when the chat view truncates.",
        "",
        "---",
        "",
    ]
    return "\n".join(header) + "\n".join(body), disp_title, first_ts


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

    markdown, disp_title, first_ts = render_markdown(entries, session_id, cwd)

    # Stable filename: date + project + title + short session id.
    project = _slugify(os.path.basename(cwd.rstrip("/")) or "project", 24)
    short_sid = session_id.split("-")[0][:8]
    fname = f"{_date_prefix(first_ts)}_{project}_{_slugify(disp_title, 32)}_{short_sid}.md"

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        out_path = os.path.join(LOG_DIR, fname)
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(markdown)
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        # Absolutely never propagate an error into the hook runner.
        sys.exit(0)
