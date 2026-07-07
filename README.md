# Hermas — Multi-Model AI Orchestration on a Single 16 GB GPU

**An architecture case study**: how a Discord bot serves image generation, conversational AI,
prompt engineering, and a stateful text-RPG from one consumer GPU (RTX 5070 Ti, 16 GB VRAM) —
when the two largest workloads physically cannot share the card.

This repository documents the architecture of a real, running system. The interesting part is
not any single feature; it is the **resource arbitration** that lets mutually exclusive
workloads coexist on hardware that a naive design would declare insufficient.

## The Constraint

| Workload | Backend | VRAM | Residency |
|---|---|---|---|
| Image generation (Z-Image Turbo) | ComfyUI | ~14 GB, **15.7 GB peak** | on demand |
| Chat LLM (qwen3.5:9b, 16k ctx) | Ollama | ~5.9 GB | resident, 30 min |
| Prompt-expansion LLM (qwen3:14b Q4) | Ollama | ~9.3 GB | load–use–unload |
| RPG game-master LLM (qwen3:14b) | Ollama | ~9.3 GB | resident, 30 min |

Image generation peaks at 15.7 GB — within 2% of the card's capacity. **No LLM can stay
loaded while an image renders.** Yet users expect snappy chat (no 30-second model reload per
message) and image prompts enhanced by a 14B model. These requirements are in direct tension,
and resolving that tension is the core of this design.

## Key Design Decisions

Each decision is captured as an Architecture Decision Record with the alternatives that were
considered and the trade-offs that were accepted:

- [ADR-0001 — Bidirectional VRAM yielding](docs/adr/0001-bidirectional-vram-yielding.md):
  every GPU consumer evicts the other side before it runs, instead of static partitioning,
  CPU offload, or buying a second GPU.
- [ADR-0002 — Differentiated keep-alive policy](docs/adr/0002-differentiated-keep-alive.md):
  the chat model stays resident for 30 minutes; the prompt expander unloads immediately after
  every use. Same runtime, opposite policies, driven by what each workload is followed by.
- [ADR-0003 — Five-tier prompt-expansion fallback chain](docs/adr/0003-prompt-expansion-fallback-chain.md):
  local 14B model first, three free cloud models next, a small local specialist model last —
  quality-ordered degradation instead of a single point of failure.
- [ADR-0004 — Disabling model "thinking" for pipeline calls](docs/adr/0004-disable-model-thinking.md):
  reasoning-mode output silently consumed the token budget and truncated replies; turning it
  off at the API level was a reliability fix, not a performance tweak.

## Architecture

C4-style context, container, and component views, including the sequence diagram of the
arbitration path: **[docs/architecture.md](docs/architecture.md)**

At a glance:

```
Discord user ──> bot.py (asyncio, discord.py)
                   ├─ ComfyUI  (HTTP + WebSocket)   ── image generation / img2img
                   ├─ Ollama   (native API)         ── chat / expansion / RPG narration
                   ├─ OpenRouter + LM Studio        ── expansion fallback tiers
                   ├─ MemPalace (ChromaDB)          ── long-term conversational memory
                   └─ SQLite                        ── RPG game state, one row per channel
```

## What It Does

Text-to-image and image-to-image generation with LLM prompt enhancement, multi-turn chat with
both short-term (per-channel, in-RAM) and long-term (vector-store) memory, a persistent
text-RPG with an LLM game master and SQLite saves, language-learning quizzes with scheduled
daily vocabulary pushes, and roleplay conversation practice with feedback.

## Operations

Runbook, failure modes, the Prometheus/Grafana monitoring design, and an honest list of known
limitations (including the convention-based concurrency model and its single-community scale
assumption): **[docs/operations.md](docs/operations.md)**

The monitoring stack is implemented, not just planned — exporter module, scrape config, and
the provisioned dashboard are in **[monitoring/](monitoring/)**. Each dashboard panel maps a
metric back to the ADR whose invariant it makes observable.

## Stack

Python 3.11 · discord.py 2.7 · ComfyUI (Z-Image Turbo) · Ollama (qwen3 family) ·
MemPalace/ChromaDB · SQLite · Windows 11, RTX 5070 Ti 16 GB

---

*Documentation-first repository: it contains the architecture record of a private system.
Configuration is environment-variable driven; no credentials, IDs, or personal data appear
here or in the system's source.*
