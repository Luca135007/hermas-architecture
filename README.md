[繁體中文](README.zh-TW.md) | **English**

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
| Image generation (Z-Image Turbo, NVFP4 weights since 2026-08) | ComfyUI | ~7.2 GB | on demand |
| Local LLM (qwen3.5:9b, 16k ctx) — chat, both RPG engines, prompt expansion | Ollama | 5.8 GB (measured 2026-10-02) | resident, 30 min |

With the original bf16 weights, image generation peaked at 15.7 GB — within 2% of the card's
capacity — so no LLM could stay loaded while an image rendered. Since 2026-08 the NVFP4 weights
need about 7.2 GB and the chat model can stay resident beside them, but a render with the card
shared measured 15.5 s against 8.8 s with the card to itself, so production keeps yielding on
(ADR-0001). Users expect snappy chat (no 30-second model reload per message), LLM-enhanced image
prompts and fast renders; balancing those is the core of this design. Since 2026-10-02 a single Ollama model
serves every local LLM workload (ADR-0006); cloud fallbacks are unchanged.

## Key Design Decisions

Each decision is captured as an Architecture Decision Record with the alternatives that were
considered and the trade-offs that were accepted:

- [ADR-0001 — Bidirectional VRAM yielding](docs/adr/0001-bidirectional-vram-yielding.md):
  every GPU consumer evicts the other side before it runs, instead of static partitioning,
  CPU offload, or buying a second GPU.
- [ADR-0002 — Differentiated keep-alive policy](docs/adr/0002-differentiated-keep-alive.md):
  the chat model stays resident for 30 minutes; the prompt expander originally unloaded
  immediately after every use (superseded in part by ADR-0006, which gives it the chat
  model's policy).
- [ADR-0003 — Five-tier prompt-expansion fallback chain](docs/adr/0003-prompt-expansion-fallback-chain.md):
  local model first, three free cloud models next, a small local specialist model last —
  quality-ordered degradation instead of a single point of failure.
- [ADR-0004 — Disabling model "thinking" for pipeline calls](docs/adr/0004-disable-model-thinking.md):
  reasoning-mode output silently consumed the token budget and truncated replies; turning it
  off at the API level was a reliability fix, not a performance tweak.
- [ADR-0005 — Placeholder IDs in few-shot prompts](docs/adr/0005-placeholder-ids-in-few-shot-prompts.md):
  the example chapter title was copied verbatim and the example's named character kept resurfacing;
  small local models treat concrete example content as reusable, not just illustrative.
- [ADR-0006 — One resident Ollama model for every local LLM workload](docs/adr/0006-single-resident-local-llm.md):
  chat, both RPG engines and prompt expansion all use `qwen3.5:9b` with identical
  `keep_alive` and `num_ctx`; the 14B model was removed.

## Architecture

C4-style context, container, and component views, including the sequence diagram of the
arbitration path: **[docs/architecture.md](docs/architecture.md)**

At a glance:

```
Discord user ──> bot.py (asyncio, discord.py)
                   ├─ ComfyUI  (HTTP + WebSocket)   ── image generation / img2img
                   ├─ Ollama   (native API)         ── chat / expansion / RPG narration
                   ├─ OpenRouter + LM Studio        ── expansion fallback tiers
                   ├─ Claude API (tarot_lib)        ── tarot reading, local rule-based fallback
                   ├─ MemPalace (ChromaDB)          ── long-term conversational memory
                   └─ SQLite                        ── RPG game state, one row per channel
```

## What It Does

Text-to-image and image-to-image generation with LLM prompt enhancement, multi-turn chat with
both short-term (per-channel, in-RAM) and long-term (vector-store) memory, a persistent
text-RPG with an LLM game master and SQLite saves — including a second, independently-gated
adult-content variant restricted to age-restricted Discord channels, whose content safety
(age whitelisting, intimacy gating, image-prompt filtering) is enforced in code rather than by
prompt instruction — language-learning quizzes with scheduled daily vocabulary pushes,
roleplay conversation practice with feedback, and a tarot-reading
feature (single-card and three-card spreads) whose interpretation runs on the Claude API when
available and degrades to a local rule-based reading otherwise — a cloud workload that draws no
VRAM and therefore sits outside the ComfyUI/Ollama arbitration entirely.

## Operations

Runbook, failure modes, the Prometheus/Grafana monitoring design, and an honest list of known
limitations (including the convention-based concurrency model and its single-community scale
assumption): **[docs/operations.md](docs/operations.md)**

The monitoring stack is implemented, not just planned — exporter module, scrape config, and
the provisioned dashboard are in **[monitoring/](monitoring/)**. Each dashboard panel maps a
metric back to the ADR whose invariant it makes observable.

## Stack

Python 3.11 · discord.py 2.7 · ComfyUI (Z-Image Turbo) · Ollama (qwen3.5:9b) ·
MemPalace/ChromaDB · SQLite · Windows 11, RTX 5070 Ti 16 GB

---

*Documentation-first repository: it contains the architecture record of a private system.
Configuration is environment-variable driven; no credentials, IDs, or personal data appear
here or in the system's source.*
