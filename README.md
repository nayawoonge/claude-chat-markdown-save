# Claude Chat Markdown Save

**English** · [한국어](README.ko.md)

A tiny [Claude Code](https://code.claude.com) plugin that **auto-saves every session as a Markdown file** — so long conversations are never lost when the chat view scrolls away or truncates old messages.

---

## Why?

The VS Code / editor chat panel only keeps so much on screen. When a session gets long, old turns scroll out of view and can be hard — or impossible — to get back to. Your conversation is *not* actually deleted (Claude Code keeps a JSONL transcript under `~/.claude/projects/…`), but that file is machine-oriented and changes format between releases.

This plugin turns that transcript into a **clean, human-readable Markdown file**, appending new turns **on every stop**, so the file always holds the *complete* session.

## What you get

- **One `.md` file per session, named after the session title** — e.g. `~/claude-logs/fix-login-bug.md`
- The conversation as it happened: your prompts (`🧑 User`) and Claude's replies (`🤖 Claude`), plus (collapsible) tool calls & results
- **Grow-only append** → each new turn is added to the file; already-saved turns are never rewritten. Even if Claude Code compacts the context and the source transcript drops early messages, they stay in your `.md`.
- **The same file keeps updating** as you keep chatting. If Claude renames the session mid-way, the plugin **renames the existing file** instead of leaving a new one behind — so you never end up with duplicate files for one session.
- Two different sessions that happen to share a title are kept apart with a short id suffix (e.g. `fix-login-bug-2bdf2c7b.md`).

## Install

From the CLI (recommended — an HTTPS URL avoids any SSH setup):

```bash
claude plugin marketplace add https://github.com/nayawoonge/claude-chat-markdown-save.git
claude plugin install claude-chat-markdown-save@nayawoonge-plugins
```

Or, inside an interactive `claude` session, with the `/plugin` command:

```
/plugin marketplace add https://github.com/nayawoonge/claude-chat-markdown-save.git
/plugin install claude-chat-markdown-save@nayawoonge-plugins
```

That's it. From now on, every session is saved to `~/claude-logs/`.

> Requires `python3` on your PATH (bundled on macOS and most Linux; on Windows use WSL or install Python).

## Just the chat, no tool noise

By default the log includes the assistant's tool calls and their results in collapsible blocks. If you only want the **plain conversation — your inputs and Claude's outputs** — turn tools off by adding this line to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
export CLAUDE_LOG_INCLUDE_TOOLS=0
```

Then open a new terminal (or run `source ~/.zshrc`). The resulting file is a clean back-and-forth:

```markdown
### 🧑 User · 2026-06-29 07:34:06

Can you recover the session I just archived?

### 🤖 Claude · 2026-06-29 07:34:26

Found it. The session you archived is "Qdrant vector storage visualization"…
```

## Configuration

All optional — set as environment variables (e.g. in your shell profile):

| Variable | Default | Meaning |
| --- | --- | --- |
| `CLAUDE_LOG_DIR` | `~/claude-logs` | Where the Markdown files go |
| `CLAUDE_LOG_INCLUDE_THINKING` | `0` | `1` to include the model's thinking blocks |
| `CLAUDE_LOG_INCLUDE_TOOLS` | `1` | Master switch for tool output. `0` keeps only the chat (hides both calls and results) |
| `CLAUDE_LOG_INCLUDE_TOOL_CALLS` | follows `…_TOOLS` | `0` hides tool **calls** — the bash commands the model runs |
| `CLAUDE_LOG_INCLUDE_TOOL_RESULTS` | follows `…_TOOLS` | `0` hides tool **results** — the command output |
| `CLAUDE_LOG_MAX_TOOL_CHARS` | `1500` | Truncate long tool input/output to N chars |

`CLAUDE_LOG_INCLUDE_TOOLS` is the master switch; the two `…_TOOL_CALLS` / `…_TOOL_RESULTS` flags let you control each independently.

Example — save into the current project folder and keep only the chat:

```bash
export CLAUDE_LOG_DIR="./.claude-logs"
export CLAUDE_LOG_INCLUDE_TOOLS=0
```

Example — **keep the thinking, but hide the bash commands** (and their output):

```bash
export CLAUDE_LOG_INCLUDE_THINKING=1
export CLAUDE_LOG_INCLUDE_TOOLS=0
```

Example — show the commands, but hide their (often noisy) output:

```bash
export CLAUDE_LOG_INCLUDE_TOOL_RESULTS=0
```

## How it works

The plugin registers a [`Stop` hook](https://code.claude.com/docs/en/hooks-guide). When Claude finishes responding, Claude Code runs `scripts/save_transcript.py` and passes it the session's `transcript_path` on stdin. The script parses the JSONL transcript and appends any new turns to the Markdown file.

Each turn is written with a hidden `<!-- turn: id -->` marker. On the next stop the script reads the existing file, sees which turns are already there, and appends only the new ones — so the log is **grow-only** and a turn is never lost even if the source transcript later drops it (e.g. after `/compact`).

The transcript format is internal to Claude Code and can change between versions, so the parser is deliberately defensive: unknown line types are skipped, missing fields fall back to defaults, and the script **never raises** into the hook runner — a parsing failure just means that one stop produces no update, it never blocks Claude.

## Where things live

| What | Path |
| --- | --- |
| Your Markdown logs (the output) | `~/claude-logs/` |
| The plugin's code (installed) | `~/.claude/plugins/marketplaces/nayawoonge-plugins/` |
| Original transcripts (Claude Code's own store) | `~/.claude/projects/<project>/<session>.jsonl` |

## Privacy

Everything runs **locally**. Nothing is uploaded anywhere. The generated `.md` files contain your full conversation, so treat them like any other local notes — the included `.gitignore` keeps `claude-logs/` out of git by default.

## Manual / one-off use

You can also run the converter by hand on any existing transcript:

```bash
echo '{"transcript_path":"'"$HOME"'/.claude/projects/<proj>/<session>.jsonl","session_id":"<session>","cwd":"'"$PWD"'"}' \
  | python3 scripts/save_transcript.py
```

## License

MIT © nayawoonge
