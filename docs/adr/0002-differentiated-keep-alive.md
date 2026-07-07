# ADR-0002 — Differentiated keep-alive Policy per LLM Workload

**Status**: Accepted (2026-07)

## Context

Ollama's `keep_alive` parameter controls how long a model stays in VRAM after a request.
A uniform policy is simplest, but the three LLM workloads have opposite usage patterns:

| Workload | Typical pattern | What follows the call |
|---|---|---|
| Chat (qwen3.5:9b, 5.9 GB) | bursts of consecutive turns | usually another chat turn |
| RPG narration (qwen3:14b) | bursts of consecutive turns | usually another turn |
| Prompt expansion (qwen3:14b) | one call per image request | **always an image render** |

Model load from disk costs 15–50 seconds. With a uniform `keep_alive: 0`, every chat turn
paid that penalty — conversation felt broken. With a uniform long keep-alive, every image
render found the card occupied and depended on eviction (ADR-0001) plus a reload of the
image model, adding latency exactly where users are most impatient.

## Decision

Set `keep_alive` per workload, by what the workload is *followed by*:

- **Chat / RPG: `keep_alive: "30m"`.** Consecutive turns hit a warm model; only the first
  message after a long pause (or after an image render evicted it) pays the reload.
- **Prompt expansion: `keep_alive: 0`.** The expander's output feeds directly into an image
  render that needs the full card, so keeping it warm would guarantee an eviction moments
  later. It unloads itself as it finishes.

Supporting configuration (Ollama service level): `OLLAMA_FLASH_ATTENTION=1` and
`OLLAMA_KV_CACHE_TYPE=q8_0`, which is what brings the 9B chat model at 16k context down to
5.9 GB — cheap enough to *afford* pinning for 30 minutes.

## Alternatives Considered

1. **Uniform `keep_alive: 0`** — correct for VRAM, terrible for conversation latency.
2. **Uniform long keep-alive** — optimizes chat, taxes every image render, and made image
   VRAM pressure dependent on chat history (the "random failure" of ADR-0001's context).
3. **Predictive preloading** (warm the model users will need next) — over-engineering for a
   two-workload system; the follow-up heuristic in the table above already encodes the
   prediction statically.

## Consequences

- Continuous chat is reload-free; the common interactive path feels instantaneous.
- The policy encodes a workload dependency graph in a single parameter — cheap to read,
  cheap to change, no scheduler code.
- The 30-minute residency means the eviction in ADR-0001 is *load-bearing*: image requests
  arriving mid-conversation rely on it. The two decisions are a pair, not independent.
