# Architecture

C4-style views of Hermas, from system context down to the components that implement the
VRAM arbitration. Diagrams are Mermaid; GitHub renders them natively.

## Level 1 — System Context

```mermaid
graph TB
    user([Discord users])
    subgraph host["Single Windows host · RTX 5070 Ti 16 GB"]
        hermas["Hermas bot<br/>(Python / discord.py)"]
        comfy["ComfyUI<br/>image generation"]
        ollama["Ollama<br/>local LLM runtime"]
        lms["LM Studio<br/>fallback LLM runtime"]
    end
    discord["Discord API"]
    openrouter["OpenRouter<br/>(free cloud models)"]

    user -->|commands & replies| discord
    discord <-->|gateway websocket| hermas
    hermas -->|HTTP + WS| comfy
    hermas -->|native API| ollama
    hermas -->|OpenAI-compatible API| lms
    hermas -->|HTTPS, optional| openrouter
```

Everything latency-critical runs on one host. OpenRouter is the only cloud dependency and is
used exclusively as a fallback tier — the system has no cloud LLM dependency; every feature
works with local inference only.

## Level 2 — Containers

```mermaid
graph TB
    subgraph bot["bot.py — asyncio event loop"]
        cmds["Command handlers<br/>image / chat / RPG / quiz"]
        arb["VRAM arbitration<br/>free_ollama_vram · free_comfyui_vram"]
        expand["Prompt expansion<br/>5-tier fallback chain"]
        memory["Memory layer<br/>per-channel RAM history + MemPalace recall"]
        rpg["RPG engine (rpg_lib)<br/>state machine + GM prompting"]
    end
    comfy["ComfyUI :8188"]
    ollama["Ollama :11434"]
    lms["LM Studio :1234"]
    openrouter["OpenRouter<br/>(fallback tiers 2-4)"]
    chroma[("MemPalace<br/>ChromaDB")]
    sqlite[("SQLite<br/>saves: one row per channel")]

    cmds --> arb
    cmds --> expand
    cmds --> memory
    cmds --> rpg
    arb -->|"/free"| comfy
    arb -->|"/api/ps → keep_alive:0"| ollama
    expand --> ollama
    expand -->|"HTTPS"| openrouter
    expand --> lms
    memory --> chroma
    rpg --> sqlite
    rpg --> ollama
    cmds -->|"POST /prompt · WS events · GET /history"| comfy
```

Blocking I/O (HTTP, WebSocket, LLM calls) is pushed off the event loop with
`asyncio.to_thread`, so an image render (~20 s, up to a minute worst-case with eviction and
cold load) never blocks chat commands from being accepted. Completion of an image job is detected by listening for `executing` /
`execution_error` events on ComfyUI's WebSocket rather than polling.

## Level 3 — The Arbitration Path

The component that makes the whole thing work. Both directions follow the same shape:
*evict the other side, then run.*

```mermaid
sequenceDiagram
    participant U as User
    participant B as bot.py
    participant O as Ollama
    participant C as ComfyUI

    Note over U,C: "!生圖" — image generation (LLM yields to image)
    U->>B: !生圖 prompt
    B->>C: POST /free
    Note right of C: image model evicted so the 14B expander fits
    B->>O: expand prompt (qwen3:14b, keep_alive:0)
    Note right of O: expander unloads itself after the call
    B->>O: /api/ps → keep_alive:0 for any resident model
    Note right of O: chat model evicted (free_ollama_vram)
    B->>C: POST /prompt (queue workflow)
    C-->>B: WS: executing → done
    B->>C: GET /history/{id}
    B-->>U: image

    Note over U,C: "!聊天" — chat (image model yields to LLM)
    U->>B: !聊天 message
    B->>C: POST /free
    Note right of C: image model evicted (free_comfyui_vram)
    B->>O: chat (qwen3.5:9b, keep_alive:30m)
    O-->>B: reply (model stays resident)
    B-->>U: reply
```

Key properties:

- **Eviction is explicit and caller-driven.** `free_comfyui_vram()` posts to ComfyUI's
  `/free` endpoint; `free_ollama_vram()` lists loaded models via `/api/ps` and unloads each
  with a zero `keep_alive`. Every GPU-bound entry point calls the appropriate one first.
- **Residency is policy, not accident.** The chat and RPG models are pinned for 30 minutes
  (consecutive turns pay no reload); the expansion model uses `keep_alive: 0` because an
  image render — which needs the whole card — always follows it (see ADR-0002).
- **Coordination is convention, not mutex.** There is deliberately no lock or queue around
  the GPU; the trade-off and its scale boundary are documented in ADR-0001 and in
  [operations.md](operations.md#known-limitations).

## Data & State

| State | Store | Lifetime | Notes |
|---|---|---|---|
| Chat history | in-process dict, per channel | until restart | capped at 20 messages/channel |
| Long-term memory | MemPalace (ChromaDB) | persistent | recall: similarity ≥ 0.6, top 3, injected into system prompt; new conversations mined in a background thread |
| RPG saves | SQLite, `saves(channel_id PK, state_json, updated_at)` | persistent | full game state serialized per channel; last 3 turns re-injected into the GM prompt each turn |
| Configuration | environment variables (`.env`) | — | every setting has a code default; no secrets in code |
