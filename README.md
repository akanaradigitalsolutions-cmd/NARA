# NARA — Neural Assistant · Responsive · Autonomous

A JARVIS-style hybrid AI assistant for macOS (Apple Silicon). NARA lives on your
Mac, uses your **Obsidian vault as long-term memory**, talks to you by **voice**,
and can drive real software development through **Claude Code**.

It is **hybrid by design**: small local models handle voice, intent, and quick
chat; **cloud Claude** does the heavy reasoning; **Claude Code** does the actual
coding in your repos. On a 16 GB machine the cloud is the main brain and the
local model keeps things fast and private — that split is the whole point.

> **Status: Phase 0 — Foundations.** The project skeleton, config loading, and a
> runnable entry point are in place. Features arrive phase by phase (see the
> roadmap below).

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
│   ├── orchestrator.py      # the "consciousness" loop             (Phase 0 stub)
│   ├── router.py           # local vs cloud vs Claude Code        (Phase 2)
│   ├── memory.py           # vault RAG + short-term context       (Phase 1)
│   └── skills/             # vault, dev, macos, web               (Phase 2/3/7)
├── voice/                  # wake.py, stt.py, tts.py              (Phase 4)
├── mcp/servers.json        # Obsidian + filesystem MCP template
├── scripts/index_vault.py  # (re)build the vector index          (Phase 1)
└── tests/                  # smoke tests
```

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
3. **Claude Code** (needs Node.js), for Phase 3 dev delegation:
   ```bash
   npm install -g @anthropic-ai/claude-code
   claude login            # or set ANTHROPIC_API_KEY
   ```

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

# 3. Configure secrets and settings
cp .env.example .env           # then paste your ANTHROPIC_API_KEY
$EDITOR config/nara.yaml       # set vault.path to your Obsidian vault
```

## Run it (Phase 0)

```bash
python -m core.orchestrator
# or, since the package installs a console script:
nara
```

You should see a **`NARA online`** banner, the resolved configuration, and a
preflight check for your API key and vault path.

## Configuration

Everything behavioural lives in [`config/nara.yaml`](config/nara.yaml); secrets
live in `.env` (never committed). Key things to set before Phase 1:

| Key | What it is |
|-----|------------|
| `vault.path` | Absolute path to your Obsidian vault |
| `models.cloud_model` | Default cloud brain (e.g. `claude-sonnet-5`) |
| `models.voice_model` | Small resident local model (e.g. `qwen3:4b`) |
| `models.embedding_model` | Ollama embedding model for vault RAG |

Run tests with `pytest`.

---

## Roadmap

| Phase | Milestone | You can… |
|-------|-----------|----------|
| **0 ✓** | Foundations | Run the skeleton; it prints `NARA online` |
| **1** | The Brain | Ask about your notes; NARA recalls from the vault |
| **2** | Core Agent (text loop) | Hold a memory-grounded conversation in the terminal (MVP) |
| **3** | Claude Code integration | "Add Stripe webhooks to Relaxha" → it happens |
| **4** | Voice | Talk to it hands-free ("Hey Nara…") |
| **5** | Desktop app | Menu-bar app with a HUD chat/voice window |
| **6** | Local + hybrid routing | Local-first, deliberate cloud, visible cost |
| **7** | Skills & automations | Control the Mac + run business workflows |
| **8** | Hardening | Restart-safe, secure, daily-driver ready |

The MVP is **Phases 0–2**. Each phase after that is independently valuable.

## Privacy & cost notes

- **Mic privacy** (Phase 4/8): wake-word gating + a visible listening indicator
  + a hard mute are non-negotiable for an always-on assistant.
- **Sensitive vault folders never leave the machine** — anything under the
  `private_folder` is answered locally only, never sent to the cloud.
- **Cloud spend is deliberate** (Phase 6): light tasks → Haiku 4.5, most
  reasoning → Sonnet 5, hardest → Opus 4.8, with a monthly budget cap.
