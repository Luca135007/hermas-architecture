# ADR-0001 — Bidirectional VRAM Yielding Between Image Generation and LLMs

**Status**: Accepted (2026-07) · **Supersedes**: one-directional yielding (image → LLM only)

## Context

The system runs on a single RTX 5070 Ti with 16 GB of VRAM. Measured peak usage during image
generation is **15.7 GB** — the image model effectively needs the entire card. The chat model
(qwen3.5:9b at 16k context) needs 5.9 GB resident; the prompt-expansion model (qwen3:14b Q4)
needs ~9.3 GB. Image generation and any LLM cannot coexist, and the 14B expander cannot even
coexist with the image model *loaded but idle*.

An earlier iteration only yielded in one direction (ComfyUI `/free` before LLM use). Image
generation then intermittently failed or spilled to shared memory whenever the chat model
happened to be resident — a failure that depended on what a user had done in the previous
half hour, which made it look random.

## Decision

Every GPU-bound entry point **evicts the other side before it runs**:

- Before any local LLM call: `free_comfyui_vram()` → ComfyUI `POST /free` unloads the image
  model.
- Before queuing an image workflow: `free_ollama_vram()` → Ollama `GET /api/ps`, then a
  zero-`keep_alive` request per loaded model, evicting whatever is resident.

Arbitration is caller-driven and convention-based: there is **no lock, queue, or resource
manager**. Each handler is responsible for clearing its own runway.

## Alternatives Considered

1. **Static partitioning (smaller models that fit together).** Rejected: an image model small
   enough to leave room for a useful LLM produces visibly worse images; a chat model small
   enough to fit alongside the image model failed a blind quality test against qwen3.5:9b.
2. **CPU offload / shared-memory spillover.** Rejected: spillover turns a 20-second render
   into minutes and is the exact failure mode this design removes.
3. **Second GPU or cloud generation.** Rejected on cost, and it dissolves the design problem
   instead of solving it — the constraint is the point of this system.
4. **Central GPU broker with a queue.** Deferred: correct at multi-user scale, but adds a
   serialization point and failure modes that a single-community deployment does not need
   yet. Revisit if concurrent GPU commands become common (see Consequences).

## Consequences

- Image generation is predictable again: it always starts with a clean card.
- Each direction pays an eviction cost of a few seconds; LLM-after-image additionally pays a
  model reload (mitigated by the keep-alive policy, ADR-0002).
- **Known limitation**: two GPU commands arriving in the same instant can interleave their
  evictions (A evicts, B evicts, A loads, B loads → contention). Accepted at current scale —
  one small community, sub-minute jobs, and the failure is a slow response rather than
  corruption. The upgrade path is the deferred broker in alternative 4.
