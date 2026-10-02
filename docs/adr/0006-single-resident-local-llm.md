# ADR-0006 — One Resident Ollama Model for Every Local LLM Workload

**Status**: Accepted (2026-10-02) · **Partially supersedes**: ADR-0001 (the 14B expander), ADR-0002 (expansion `keep_alive: 0`), ADR-0003 (tier 1 model)

## Context

Until this change the local LLM workloads used two Ollama models: `qwen3.5:9b` for chat and the
adult-content RPG, and `qwen3:14b` for the wuxia RPG narrator and for prompt expansion (tier 1 of
the fallback chain, ADR-0003). The 14B model occupied 9.3 GB on disk.

Prompt expansion also called Ollama with `keep_alive: 0` and `num_ctx: 4096`, while chat used
`keep_alive: "30m"` and `num_ctx: 16384`. If one model serves both, mismatched parameters make an
expansion call either unload the model afterwards or reload it at a different context size.

The decision was informed by a new A/B script, `research/narrator_ab.py` (not part of this
repository). It feeds fixed inputs to both models for three uses, one sample per prompt. Results
from 2026-10-02 (9b vs 14b):

| Use | Median time | Other observations |
|---|---|---|
| Adult RPG, 10 turns | 13.9 s vs 14.9 s | warnings caught by code: 9 vs 4 |
| Wuxia RPG, 8 turns | 5.5 s vs 7.1 s | missing JSON, re-prompted: 2 vs 5 |
| Prompt expansion, 6 prompts | 2.8 s vs 3.0 s | both preserved the required text |
| Cold load | 23.6 s vs 45.2 s | |

The maintainer also read blind-labelled outputs (labels assigned to models in random order) and preferred the 9b output,
judging its logic more coherent. Only one of the three blind files was reviewed.

A check of Hugging Face on 2026-10-02 found no Qwen language model of 14B or smaller newer than
Qwen3.5 (Qwen3.6 and 3.8 exist only at 27B and above).

## Decision

Use a single Ollama model, `qwen3.5:9b` (6.6 GB on disk), for chat, the adult-content RPG, the
wuxia RPG narrator and prompt expansion (tier 1 of the ADR-0003 chain). `qwen3:14b` was deleted
from the machine.

Prompt-expansion calls now use `keep_alive: "30m"` and `num_ctx: 16384`, identical to chat.
Verification: a call with chat parameters (cold load, `load_duration` 16.16 s) followed by a call
with expansion parameters gave `load_duration` 0.0 s, and `/api/ps` showed one qwen3.5:9b at
5.8 GB with context 16384.

The VRAM yielding of ADR-0001 is unchanged: `VRAM_YIELD_ENABLED` is still on in production, so
`free_ollama_vram()` still unloads the 9b model before an image renders.

## Alternatives Considered

1. **Keep qwen3:14b for narration and expansion.** Not chosen: in the A/B run it was slower, had
   more missing-JSON re-prompts in the wuxia test and a slower cold load, the maintainer preferred
   the 9b output, and keeping it meant two models to load and evict instead of one. Its
   advantages were fewer code-caught warnings in the adult RPG test (4 vs 9) and no restated
   openings in the wuxia test (0 vs 2); 9b in turn needed no fallback option generation in the
   adult RPG test (0 vs 2).
2. **Upgrade to a 27B-class model.** Not chosen: the Hugging Face check found no newer Qwen
   language model at 14B or below, and the newer releases found start at 27B. No 27B model was
   tested here.

## Consequences

- One Ollama model on disk and in VRAM for all local LLM workloads (the cloud tiers of ADR-0003
  and the small LM Studio fallback are unchanged); no model switch between chat, RPG and
  expansion.
- Because expansion and chat share parameters, an expansion call no longer unloads the model or
  triggers a reload at a different context size.
- The model is still evicted before each image render (ADR-0001), so the first LLM call after a
  render pays a reload.
- The narrator comparison is one sample per prompt and only part of the blind review was read;
  it is evidence for this decision, not a measured quality rate.
- Program-side warnings are higher with 9b in the adult RPG test (9 vs 4); the code-side checks
  remain necessary.
