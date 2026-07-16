# Claude Chat Markdown Save

[English](README.md) · **한국어**

긴 대화가 위로 밀려 사라져도 걱정 없게, **각 Claude Code 세션 전체를 계속 `.md` 파일로 저장**해 주는 [Claude Code](https://code.claude.com) 플러그인입니다.

---

## 왜 필요한가요?

VS Code(또는 에디터) 채팅 패널은 화면에 보이는 양이 제한적이라, 대화가 길어지면 예전 메시지가 위로 밀려 다시 보기 어렵습니다. 실제로 삭제되는 건 아니지만(원본은 `~/.claude/projects/…`에 JSONL로 저장됨) 그 파일은 사람이 읽기 불편하고 포맷도 버전마다 바뀝니다.

이 플러그인은 그 기록을 **읽기 좋은 마크다운**으로 바꿔, **응답이 끝날 때마다** 새 대화를 이어 붙여 저장합니다. 그래서 파일에는 항상 *전체* 세션이 담깁니다.

## 무엇이 저장되나요?

- **세션당 `.md` 파일 하나**, 파일명은 **세션 제목** — 예: `~/claude-logs/로그인-버그-수정.md`
- 실제 대화 그대로 — 당신의 입력(`🧑 User`)과 Claude의 답변(`🤖 Claude`), 그리고 (접히는) 도구 호출·결과
- **누적 저장(grow-only)** → 새 턴만 뒤에 덧붙이고, 이미 저장된 내용은 다시 쓰지 않습니다. Claude Code가 컨텍스트를 압축해 원본에서 앞 대화가 사라져도, 당신의 `.md`에는 그대로 남습니다.
- **같은 파일이 계속 갱신**됩니다. 대화 중 Claude가 세션 제목을 바꾸면, 새 파일을 만들지 않고 **기존 파일의 이름만 바꿔** 이어씁니다 — 한 세션에 파일이 여러 개 생기지 않습니다.
- 서로 다른 세션이 우연히 같은 제목이면, 짧은 id를 붙여 구분합니다 (예: `로그인-버그-수정-2bdf2c7b.md`).

## 설치

터미널 CLI에서 (권장 — HTTPS URL이면 SSH 설정이 필요 없습니다):

```bash
claude plugin marketplace add https://github.com/nayawoonge/claude-chat-markdown-save.git
claude plugin install claude-chat-markdown-save@nayawoonge-plugins
```

또는 대화형 `claude` 세션 안에서 `/plugin` 명령으로:

```
/plugin marketplace add https://github.com/nayawoonge/claude-chat-markdown-save.git
/plugin install claude-chat-markdown-save@nayawoonge-plugins
```

끝입니다. 이제부터 모든 세션이 `~/claude-logs/`에 저장됩니다.

> `python3`가 PATH에 있어야 합니다 (macOS와 대부분의 Linux에는 기본 포함, Windows는 WSL 사용 또는 Python 설치).

## 순수 채팅만 남기기 (도구 부분 제거)

기본값은 Claude의 도구 호출과 결과까지 접히는 블록으로 함께 저장합니다. **입력·출력, 즉 순수한 대화만** 남기고 싶으면, 셸 프로필(`~/.zshrc` 또는 `~/.bashrc`)에 다음 한 줄을 추가하세요:

```bash
export CLAUDE_LOG_INCLUDE_TOOLS=0
```

그런 다음 새 터미널을 열거나 `source ~/.zshrc`를 실행하면 됩니다. 결과 파일은 깔끔한 문답 형태가 됩니다:

```markdown
### 🧑 User · 2026-06-29 07:34:06

내가 방금 보관한 세션 다시 불러와줄 수 있어?

### 🤖 Claude · 2026-06-29 07:34:26

찾았어요. 방금 보관하신 세션은 "Qdrant vector storage visualization" 입니다…
```

## 설정

모두 선택 사항입니다 — 환경변수로 지정합니다 (예: 셸 프로필에):

| 변수 | 기본값 | 의미 |
| --- | --- | --- |
| `CLAUDE_LOG_DIR` | `~/claude-logs` | 마크다운 파일이 저장될 위치 |
| `CLAUDE_LOG_INCLUDE_THINKING` | `0` | `1`이면 모델의 thinking(사고 과정) 블록 포함 |
| `CLAUDE_LOG_INCLUDE_TOOLS` | `1` | `0`이면 도구 호출·결과 제외 (순수 대화만) |
| `CLAUDE_LOG_MAX_TOOL_CHARS` | `1500` | 긴 도구 입력/출력을 N자로 잘라냄 |

예시 — 현재 프로젝트 폴더에 저장하고, 대화만 남기기:

```bash
export CLAUDE_LOG_DIR="./.claude-logs"
export CLAUDE_LOG_INCLUDE_TOOLS=0
```

## 동작 방식

이 플러그인은 [`Stop` 훅](https://code.claude.com/docs/en/hooks-guide)을 등록합니다. Claude가 응답을 마치면 Claude Code가 `scripts/save_transcript.py`를 실행하고, 그 세션의 `transcript_path`를 stdin으로 넘겨줍니다. 스크립트는 JSONL 트랜스크립트를 읽어 새 턴을 마크다운 파일에 이어 붙입니다.

각 턴은 보이지 않는 `<!-- turn: id -->` 마커와 함께 기록됩니다. 다음 실행 때 스크립트는 기존 파일을 읽어 이미 있는 턴을 확인하고, **새 턴만** 추가합니다 — 그래서 로그는 **오직 커지기만** 하며, 원본 트랜스크립트가 나중에 그 턴을 잃어버려도(예: `/compact` 이후) 사라지지 않습니다.

트랜스크립트 포맷은 Claude Code 내부용이라 버전마다 바뀔 수 있어서, 파서는 의도적으로 방어적으로 작성됐습니다: 모르는 라인 타입은 건너뛰고, 빠진 필드는 기본값으로 대체하며, 스크립트는 훅 러너로 **예외를 절대 던지지 않습니다** — 파싱에 실패하면 그 회차만 갱신이 안 될 뿐, Claude 동작을 막지 않습니다.

## 어디에 저장되나요?

| 항목 | 경로 |
| --- | --- |
| 마크다운 로그 (결과물) | `~/claude-logs/` |
| 플러그인 코드 (설치본) | `~/.claude/plugins/marketplaces/nayawoonge-plugins/` |
| 원본 트랜스크립트 (Claude Code 자체 저장) | `~/.claude/projects/<프로젝트>/<세션>.jsonl` |

## 개인정보

모든 처리는 **로컬에서** 이루어집니다. 어디에도 업로드되지 않습니다. 생성된 `.md` 파일에는 전체 대화가 담기므로 다른 로컬 메모처럼 취급하세요 — 포함된 `.gitignore`가 기본적으로 `claude-logs/`를 git에서 제외합니다.

## 수동 실행 (일회성)

기존 트랜스크립트에 대해 변환기를 직접 실행할 수도 있습니다:

```bash
echo '{"transcript_path":"'"$HOME"'/.claude/projects/<proj>/<session>.jsonl","session_id":"<session>","cwd":"'"$PWD"'"}' \
  | python3 scripts/save_transcript.py
```

## 라이선스

MIT © nayawoonge
