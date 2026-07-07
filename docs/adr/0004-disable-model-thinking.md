# ADR-0004 — Disable Reasoning Mode (`think: false`) for All Pipeline LLM Calls

**Status**: Accepted (2026-07)

## Context

The qwen3 model family defaults to *reasoning mode*: before the visible answer, the model
emits an internal deliberation block (`<think>…</think>`). For interactive tools that stream
and render this, it can be a feature. Inside a pipeline it caused a subtle production bug:

- Every local (Ollama) call sets `num_predict` (output token cap: 400 for expansion, 1024 for chat, 1200
  for RPG narration) to bound latency and VRAM during decode.
- Reasoning tokens **count against that cap**. On hard inputs the model spent the entire
  budget deliberating, and the visible answer arrived truncated — or empty.
- The failure was intermittent and input-dependent, and post-processing could not repair it:
  a stripping function that removes think-blocks only works when the closing tag exists,
  which is precisely what a budget-truncated response lacks.

The symptom ("replies sometimes blank or cut off, mostly on complex prompts") surfaced when
the chat model was upgraded to qwen3.5:9b, and initially looked like a model-quality problem
rather than a protocol problem.

## Decision

Pass top-level **`think: false`** on every Ollama API call in the system — chat, prompt
expansion, RPG narration, role-play conversation review. Reasoning mode is treated as an interactive
affordance that has no place in machine-to-machine calls with bounded output budgets.
Tag-stripping is retained only as a defensive layer for models that ignore the flag.

## Alternatives Considered

1. **Raise `num_predict` to leave room for reasoning.** Rejected: the deliberation length is
   unbounded and input-dependent — any fixed budget loses to some input, and larger budgets
   raise worst-case latency for every call.
2. **Strip `<think>` blocks in post-processing only.** Rejected: cannot recover the truncated
   case (no closing tag), which is the case that matters.
3. **Prompt-level instructions ("do not think").** Rejected: unreliable, and it burns prompt
   tokens to fight a switch the API exposes directly.

## Consequences

- Blank/truncated replies disappeared across all four call sites; output budgets now buy
  visible tokens only.
- Latency per call dropped (no hidden deliberation phase) — relevant on a card where every
  decoding second holds VRAM that image generation may be waiting for.
- Possible quality cost on genuinely hard reasoning tasks; none of the four call sites is
  one (they are stylistic generation and structured narration), so the trade was accepted.
- Transferable lesson: **when output is truncated, audit what shares the token budget.**
  The bug was in the accounting, not in the model.
