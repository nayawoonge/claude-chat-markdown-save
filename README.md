# Claude Chat Logger

A tiny [Claude Code](https://code.claude.com) plugin that **auto-saves every session as a Markdown file** — so long conversations are never lost when the chat view scrolls away or truncates old messages.

> 긴 대화가 위로 밀려 사라져도 걱정 없게, 각 세션 전체를 계속 `.md` 파일로 저장해 주는 Claude Code 플러그인입니다.

---

## Why? / 왜 필요한가요?

The VS Code / editor chat panel only keeps so much on screen. When a session gets long, old turns scroll out of view and can be hard — or impossible — to get back to. Your conversation is *not* actually deleted (Claude Code keeps a JSONL transcript under `~/.claude/projects/…`), but that file is machine-oriented and changes format between releases.

This plugin turns that transcript into a **clean, human-readable Markdown file**, and rewrites it **on every stop**, so the file always holds the *complete* session.

VS Code(또는 에디터) 채팅 패널은 화면에 보이는 양이 제한적이라, 대화가 길어지면 예전 메시지가 위로 밀려 다시 보기 어렵습니다. 실제로 삭제되는 건 아니지만(원본은 `~/.claude/projects/…`에 JSONL로 저장됨) 그 파일은 사람이 읽기 불편하고 포맷도 버전마다 바뀝니다. 이 플러그인은 그 기록을 **읽기 좋은 마크다운**으로 바꿔, **응답이 끝날 때마다** 전체 대화를 다시 저장합니다.

## What you get / 결과물

- One `.md` file per session, e.g. `~/claude-logs/2026-07-16_my-project_fix-login-bug_2bdf2c7b.md`
- Full conversation: your prompts, Claude's replies, and (collapsible) tool calls & results
- Rewritten on every stop → always complete, never partial
- Stable filename per session → the same file keeps updating as you keep chatting

## Install / 설치

```bash
# 1. Add this repo as a plugin marketplace
/plugin marketplace add hwangjiung/claude-chat-logger

# 2. Install the plugin
/plugin install claude-chat-logger@hwangjiung-plugins
```

Or from the CLI:

```bash
claude plugin marketplace add hwangjiung/claude-chat-logger
claude plugin install claude-chat-logger@hwangjiung-plugins --scope user
```

That's it. From now on, every session is saved to `~/claude-logs/`.

> Requires `python3` on your PATH (bundled on macOS and most Linux; on Windows use WSL or install Python).

## Configuration / 설정

All optional — set as environment variables (e.g. in your shell profile):

| Variable | Default | Meaning |
| --- | --- | --- |
| `CLAUDE_LOG_DIR` | `~/claude-logs` | Where the Markdown files go |
| `CLAUDE_LOG_INCLUDE_THINKING` | `0` | `1` to include the model's thinking blocks |
| `CLAUDE_LOG_INCLUDE_TOOLS` | `1` | `0` to omit tool calls / results |
| `CLAUDE_LOG_MAX_TOOL_CHARS` | `1500` | Truncate long tool input/output to N chars |

Example (save into the current project instead, and hide tool noise):

```bash
export CLAUDE_LOG_DIR="./.claude-logs"
export CLAUDE_LOG_INCLUDE_TOOLS=0
```

## How it works / 동작 방식

The plugin registers a [`Stop` hook](https://code.claude.com/docs/en/hooks-guide). When Claude finishes responding, Claude Code runs `scripts/save_transcript.py` and passes it the session's `transcript_path` on stdin. The script parses the JSONL transcript and (over)writes the Markdown file.

The transcript format is internal to Claude Code and can change between versions, so the parser is deliberately defensive: unknown line types are skipped, missing fields fall back to defaults, and the script **never raises** into the hook runner — a parsing failure just means that one stop produces no update, it never blocks Claude.

## Privacy / 개인정보

Everything runs **locally**. Nothing is uploaded anywhere. The generated `.md` files contain your full conversation, so treat them like any other local notes — the included `.gitignore` keeps `claude-logs/` out of git by default.

## Manual / one-off use / 수동 사용

You can also run the converter by hand on any existing transcript:

```bash
echo '{"transcript_path":"'"$HOME"'/.claude/projects/<proj>/<session>.jsonl","session_id":"<session>","cwd":"'"$PWD"'"}' \
  | python3 scripts/save_transcript.py
```

## License

MIT © hwangjiung
