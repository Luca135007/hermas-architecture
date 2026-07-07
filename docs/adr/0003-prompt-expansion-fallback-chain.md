# ADR-0003 — Five-Tier Prompt-Expansion Fallback Chain

**Status**: Accepted (2026-07) · **Supersedes**: single local specialist model (V6)

## Context

Short user prompts ("a cat in the rain") produce mediocre images; an LLM that rewrites them
into detailed, well-composed prompts measurably improves output. The original design used a
small local specialist model (Z-Image-Engineer-V6, 2.1 GB, prompt-tuned for this exact task)
as the only expander. Its quality was poor — a general 14B model with a good system prompt
beat it clearly — but the 14B model introduces new failure modes: it needs 9.3 GB of VRAM on
a card the image model also wants, takes 15–50 s to load, and can time out or return empty
output.

Expansion is an *enhancement*, not a requirement: a failed expansion should degrade image
quality, never block image generation.

## Decision

Try expanders in **descending quality order**, falling through on any exception or timeout
(the local tier additionally falls through on empty output); each tier is independent of the
previous one's infrastructure:

| Tier | Model | Where | Guard |
|---|---|---|---|
| 1 | qwen3:14b | local Ollama | 180 s timeout, `keep_alive: 0`, `think: false` |
| 2 | nemotron-3-ultra (free) | OpenRouter | skipped when no API key; 60 s timeout |
| 3 | nex-n2-pro (free) | OpenRouter | same |
| 4 | deepseek-r1 (free) | OpenRouter | same |
| 5 | Z-Image-Engineer-V6 | local LM Studio | last resort — available whenever LM Studio is running, lowest quality |

The whole chain sits behind a single feature flag (`V6_ENABLED`); disabled, images render
from the raw user prompt.

## Alternatives Considered

1. **Single local 14B expander, fail hard.** Rejected: turns an Ollama hiccup into "the bot
   can't draw," which users read as total failure.
2. **Cloud-first (OpenRouter tier 1).** Rejected: adds a network dependency to the happy
   path, free-tier models are rate-limited and variable, and local inference is private by
   default — user prompts only leave the machine when the local tier is already failing.
3. **Retry tier 1 instead of falling through.** Rejected: the common failure (VRAM pressure,
   cold-load timeout) is exactly the failure a retry repeats; a *different* backend breaks
   the correlation.
4. **Demote V6 out of the chain entirely.** Rejected: it is the only tier with no network
   dependency and a small (2.1 GB) VRAM footprint. As a terminal fallback its low quality is
   still better than raw prompts.

## Consequences

- Expansion has no single point of failure; the observed worst case is a slower, plainer
  image rather than an error message.
- Quality ordering means users get the best available result silently — but also that a
  degraded tier is *invisible* unless logged. The monitoring plan (operations.md) therefore
  tracks which tier served each request; a drift toward lower tiers is an early warning that
  tier 1 is unhealthy.
- Free cloud tiers change without notice (models get delisted or rate-limited). The chain
  makes each individual tier disposable, and tier updates are a one-line list edit.
