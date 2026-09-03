# NARA — Neural Assistant · Responsive · Autonomous

A JARVIS-style hybrid AI assistant for macOS (Apple Silicon). NARA lives on your
Mac, uses your **Obsidian vault as long-term memory**, talks to you by **voice**,
and can drive real software development through **Claude Code**.

It is **hybrid by design**: small local models handle voice, intent, and quick
chat; **cloud Claude** does the heavy reasoning; **Claude Code** does the actual
coding in your repos. On a 16 GB machine the cloud is the main brain and the
local model keeps things fast and private — that split is the whole point.

> **Status: Phase 7 — Skills & automations.** NARA now *does things*: controls
> macOS (open apps, run Shortcuts, set Focus), researches the web into your vault
> via Claude, and drafts on-brand marketing content (bilingual EN/ID) grounded in
> your notes. Run `nara skills` to see them. Hardening (Phase 8) is next.

---

## Architecture

```
🎙️  Voice        wake word → speech-to-text → text-to-speech
🧠  Orchestrator intent router + model router (local vs cloud vs Claude Code)
📓  Brain        Obsidian vault (Markdown) + local vector index (LanceDB)
⚙️  Engines      local LLM (Ollama) · cloud Claude (API) · Claude Code (Agent SDK)
🛠️  Skills       macOS control · web · business workflows
```

The connective tissue is **MCP (Model Context Protocol)**: the vault and most
skills are exposed as MCP servers, so the same Obsidian connection powers NARA's
memory *and* lets Claude Code read your notes while it codes.

## Repo layout

```
nara/
├── config/nara.yaml        # models, routes, vault path, voices  (edit this)
├── core/
│   ├── config.py           # config + .env loading                (Phase 0 ✓)
│   ├── orchestrator.py      # the agent loop + chat REPL           (Phase 2 ✓)
│   ├── router.py           # local vs cloud vs Claude Code        (Phase 2 ✓)
│   ├── engines.py          # Ollama / claude-cli / Anthropic      (Phase 2 ✓)
│   ├── persona.py          # system prompt + memory framing       (Phase 2 ✓)
│   ├── memory.py           # vault RAG: search/remember/daily     (Phase 1 ✓)
│   ├── usage.py            # per-turn usage + cost log            (Phase 6 ✓)
│   ├── service.py          # local HTTP service (FastAPI)          (Phase 5 ✓)
│   └── skills/             # dev · macos · web · content           (Phase 3/7 ✓)
├── voice/                  # stt.py, tts.py, loop.py; wake.py opt (Phase 4 ✓)
├── app/menubar.py          # macOS menu-bar app (rumps)            (Phase 5 ✓)
├── mcp/servers.json        # Obsidian + filesystem MCP template
├── scripts/                # index_vault, set_vault, add_project, install_menubar
└── tests/                  # unit tests (offline)
```

---

## Quickstart (macOS, from scratch)

Starting from a fresh Mac with no dev tools? Run these in **Terminal**, in order:

```bash
# 1) Homebrew — the macOS package manager (also installs git). When it finishes,
#    follow its "Next steps" to add brew to your PATH, then reopen Terminal.
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 2) The toolchain
brew install python@3.12 uv ollama node ffmpeg espeak-ng
brew services start ollama          # run Ollama in the background

# 3) Get NARA and enter the project folder
git clone https://github.com/akanaradigitalsolutions-cmd/NARA.git
cd NARA
git checkout claude/nara-project-setup-uk0hl9

# 4) Set up the environment + brain (venv, install, pull the embedding model)
bash scripts/setup_mac.sh

# 5) Activate the env, point NARA at your vault, then build the index and search
source .venv/bin/activate
python scripts/set_vault.py --list                    # show your Obsidian vaults
python scripts/set_vault.py "/Users/you/YourVault"     # ...then set the right one
#   no vault yet?  python scripts/set_vault.py --create ~/NARA-Vault
python scripts/index_vault.py
python -m core.memory search "Relaxha pricing"
```

Most of the earlier errors just mean you weren't in the `NARA` folder yet (step 3)
and the tools weren't installed (steps 1–2). The sections below explain each piece.

---

## Prerequisites (macOS, Apple Silicon)

1. **Homebrew**, then core tools:
   ```bash
   brew install python@3.12 ffmpeg espeak-ng
   ```
2. **Ollama** (local models):
   ```bash
   brew install ollama
   ollama pull qwen3:4b            # small resident model for voice/intent
   ollama pull nomic-embed-text    # embeddings for vault memory (Phase 1)
   # Optional, on demand — verify the exact 9B tag for your machine first:
   # ollama pull qwen3.5:9b
   ```
   On 16 GB, keep one small model resident; don't hold a 14B+ model — it swaps
   to SSD and crawls.
3. **Claude Code** (needs Node.js) — NARA's cloud + dev engine. With a Claude
   **Pro/Max subscription** you don't need an API key; log in and NARA drives the
   CLI on your plan:
   ```bash
   npm install -g @anthropic-ai/claude-code
   claude login            # choose "Claude account" (Pro/Max) — no API key needed
   ```
   Keep `ANTHROPIC_API_KEY` **unset** to use your subscription; set it only if you
   switch `cloud.backend` to `api` (pay-per-token, for finer model/cost control).

## Setup

```bash
# 1. Create a virtual environment (uv recommended; plain venv works too)
uv venv --python 3.12          #  … or:  python3.12 -m venv .venv
source .venv/bin/activate

# 2. Install NARA (editable). Add extras as you reach later phases:
uv pip install -e .            # base: config + cloud/local clients
# uv pip install -e ".[memory]" # Phase 1: LanceDB vector index
# uv pip install -e ".[agent]"  # Phase 3: Claude Code delegation
# uv pip install -e ".[voice]"  # Phase 4: wake word / STT / TTS
# uv pip install -e ".[all,dev]" # everything + test tooling

# 3. Configure settings (no API key needed on a Pro/Max subscription)
$EDITOR config/nara.yaml       # set vault.path; cloud.backend defaults to `cli`
cp .env.example .env           # only fill ANTHROPIC_API_KEY if cloud.backend=api
```

## Run it (Phase 0)

```bash
python -m core.orchestrator
# or, since the package installs a console script:
nara
```

You should see a **`NARA online`** banner, the resolved configuration, and a
preflight check for your cloud auth (CLI login or API key) and vault path.

## Configuration

Everything behavioural lives in `config/nara.yaml` — your own copy, created from
[`config/nara.example.yaml`](config/nara.example.yaml) on setup and **git-ignored**
so `git pull` never clobbers it. Secrets live in `.env` (also never committed).
Key things to set:

| Key | What it is |
|-----|------------|
| `cloud.backend` | `cli` (Pro/Max subscription via Claude Code) or `api` (API key) |
| `vault.path` | Absolute path to your Obsidian vault |
| `models.cloud_model` | Default cloud brain (e.g. `claude-sonnet-5`) |
| `models.voice_model` | Small resident local model (e.g. `qwen3:4b`) |
| `models.embedding_model` | Ollama embedding model for vault RAG |

Run tests with `pytest`.

## The Brain — memory (Phase 1)

NARA's memory lives in your vault plus a local vector index (LanceDB), embedded
with Ollama's `nomic-embed-text`. Install the extra and make sure Ollama is
running with the embedding model pulled:

```bash
uv pip install -e ".[memory]"
ollama pull nomic-embed-text
```

**Build the index**, then query and write memory:

```bash
python scripts/index_vault.py            # incremental (skips unchanged notes)
python scripts/index_vault.py --rebuild  # wipe and rebuild
python scripts/index_vault.py --watch     # keep it live as you edit the vault

python -m core.memory search "Relaxha pricing"                  # semantic recall
python -m core.memory remember "Villa X owner is Ketut" --tags relaxha
python -m core.memory daily "Shipped the laundry route change"
```

NARA owns a few folders inside your vault — `NARA/Memory/` (facts it learns) and
`NARA/Daily/` (daily logs). Anything under `NARA/private/` is never indexed and
never leaves the machine, and your own notes are read-only to the indexer: NARA
only writes inside its own folders. Indexing is idempotent (unchanged notes are
skipped by mtime) and fully local — no cloud, no API key.

## Chat with NARA (Phase 2)

The agent answers with a **local** model by default and **escalates to Claude**
(on your Pro/Max plan) for hard or long requests. Prerequisites:

```bash
ollama pull qwen3:4b     # local chat model (setup_mac.sh does this for you)
claude login             # for cloud answers, on your Pro/Max subscription
```

Then talk to it:

```bash
nara                     # interactive REPL (also: python -m core.orchestrator)
nara --once "what do I know about Relaxha pricing?"
nara --status            # config + preflight
```

Inside the REPL: chat normally; `remember that <fact>` saves to your vault;
`/status`, `/help`, `/exit`. Each reply shows which engine answered
(`local · ollama:qwen3:4b`, `cloud · claude-cli`, …). Routing is heuristic
(config-driven) for now and becomes a cloud-weighted policy with cost tracking in
Phase 6.

## Do my dev work (Phase 3)

NARA can hand a coding task to **Claude Code** inside one of your repos, on your
Pro/Max plan. First register a project — points a name at a local repo, no YAML
editing:

```bash
python scripts/add_project.py relaxha ~/code/relaxha
python scripts/add_project.py --list            # see configured projects
```

Then delegate:

```bash
nara dev relaxha "add a /health endpoint and a test for it"
nara dev relaxha "refactor the booking model" --dry-run   # plan only, no edits
nara dev laundraos "fix the failing CI lint" --allow-bash # also permit shell
```

NARA runs Claude Code headless with `--permission-mode acceptEdits` (file edits
auto-approved; **never** `--dangerously-skip-permissions`), then reports a summary
and the files that changed (via `git status`). It respects a `dev.max_cost_usd`
ceiling (relevant in `api` mode; on a subscription, runs are $0). You can also run
it from the chat REPL with `/dev <project> "<task>"`.

## Talk to NARA (Phase 4)

Hands-free push-to-talk: press Enter, speak, and NARA answers out loud. macOS
`say` is the built-in voice, so text-to-speech needs nothing; speech-to-text
needs one extra:

```bash
brew install portaudio          # lets the mic be recorded
uv pip install -e ".[voice]"    # faster-whisper (STT) + sounddevice
```

Then:

```bash
nara voice
```

Press **Enter**, speak, and pause — NARA transcribes with Whisper, answers (same
local/cloud routing as chat), and speaks the reply. Ctrl-C to quit. The first run
downloads the Whisper model (`voice.stt_model` in config, `small` by default),
and macOS will ask for **microphone permission** once.

Always-on **"Hey Nara"** wake word is an optional add-on (`.[wake]`,
openWakeWord); push-to-talk is the reliable default.

## Desktop app (Phase 5)

Give NARA a **menu-bar presence** and start it at login — a lightweight
pure-Python path (no Rust/Node build):

```bash
uv pip install -e ".[menubar]"       # rumps (macOS only)
nara menubar                          # run it now…
python scripts/install_menubar.py     # …or start it automatically at login
```

The menu-bar icon opens NARA's chat (`nara`) or voice (`nara voice`) in a
Terminal, reindexes the vault, or shows status. Remove the login item with
`python scripts/install_menubar.py --uninstall`.

There's also a **local HTTP service** so any UI or script can reach the same core:

```bash
uv pip install -e ".[service]"
nara serve                            # http://127.0.0.1:8765
# GET /status  ·  POST /chat {"message": "…"}  ·  POST /reindex
```

A richer native HUD (Tauri or SwiftUI) can be layered on this service later —
the decoupling is what makes that straightforward.

## Local-first routing & cost (Phase 6)

NARA is deliberate about the cloud — no new setup, it's automatic:

- **Privacy** — a message matching `privacy.sensitive_keywords` (password, bank,
  medical, …) is answered **on-device only**, never sent to the cloud.
- **Escalation** — if the local model's answer looks unsure, NARA quietly
  re-asks **Claude** for a better one (unless it's private or over budget).
- **Warm model** — the local model is kept loaded (`models.keep_alive`) so
  replies stay snappy.
- **Budget** — cloud spend is tracked against `budget.monthly_cloud_usd`; over
  the cap, cloud calls fall back to local (on a subscription, spend is $0).

See your local-vs-cloud split and spend any time:

```bash
nara stats
```

Every reply also shows its route inline — `local`, `cloud`, or `cloud+esc`
(escalated). The raw log lives at `~/.nara/logs/usage.jsonl`.

## Skills & automations (Phase 7)

NARA stops being just a chat box and starts *doing things*. See everything it can
do at a glance:

```bash
nara skills
```

**Control your Mac** — open apps, run any Shortcut you've built, or set a Focus
mode (macOS-only; each uses `osascript` / the `shortcuts` CLI):

```bash
nara macos open Obsidian
nara macos shortcut "Morning Routine"
nara macos focus Work            # runs your Focus-named Shortcut
nara macos list                  # list your Shortcuts
```

**Research the web into your vault** — the work is delegated to Claude (which has
web search + fetch), so it runs on your Pro/Max subscription with no extra API.
The summary is saved as a note under `NARA/Web/`:

```bash
nara web search "Bali spa marketing trends 2026"
nara web url https://example.com/some-article
```

**Draft marketing content** grounded in your own vault notes — captions, listing
copy, or partner outreach for Relaxha / the laundry, optionally **bilingual**
(Bahasa Indonesia + English). Drafts land under `NARA/Content/`:

```bash
nara draft "weekend spa promo" --kind caption --bilingual
nara draft "new villa laundry service" --kind listing
nara draft "collab with a yoga studio" --kind outreach
```

Configure where notes are saved with `web.save_folder` / `content.save_folder`,
and how many vault notes seed a draft with `content.search_k`. In the chat REPL,
`/skills` shows the same list.

---

## Roadmap

| Phase | Milestone | You can… |
|-------|-----------|----------|
| **0 ✓** | Foundations | Run the skeleton; it prints `NARA online` |
| **1 ✓** | The Brain | Index + recall your vault; `remember` / `daily_log` |
| **2 ✓** | Core Agent (text loop) | Hold a memory-grounded conversation in the terminal (MVP) |
| **3 ✓** | Claude Code integration | "Add Stripe webhooks to Relaxha" → it happens |
| **4 ✓** | Voice | Talk to it hands-free (`nara voice`, push-to-talk) |
| **5 ✓** | Desktop app | Menu-bar app (launch-at-login) + local service |
| **6 ✓** | Local + hybrid routing | Local-first, deliberate cloud, visible cost (`nara stats`) |
| **7 ✓** | Skills & automations | Control the Mac, research the web, draft content (`nara skills`) |
| **8** | Hardening | Restart-safe, secure, daily-driver ready |

The MVP is **Phases 0–2**. Each phase after that is independently valuable.

## Privacy & cost notes

- **Mic privacy** (Phase 4/8): wake-word gating + a visible listening indicator
  + a hard mute are non-negotiable for an always-on assistant.
- **Sensitive vault folders never leave the machine** — anything under the
  `private_folder` is answered locally only, never sent to the cloud.
- **On a Pro/Max subscription** (`cloud.backend: cli`), cloud + Claude Code usage
  counts against your plan's shared quota (no per-token bill). Note that quota is
  shared with claude.ai and Claude Desktop.
- **Cloud spend is deliberate** in `api` mode (Phase 6): light tasks → Haiku 4.5,
  most reasoning → Sonnet 5, hardest → Opus 4.8, with a monthly budget cap.
