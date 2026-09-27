# ADR-0005 — Placeholder IDs in Few-Shot Prompts (Small Models Copy Examples Verbatim)

**Status**: Accepted (2026-09)

## Context

The adult-content RPG engine (`jpm_lib`) asks the GM model — the same 9B-class model used for
chat (`qwen3.5:9b`, `think: false`, per ADR-0004) — to open each turn with a chapter title and
close it with a JSON delta, following a worked example embedded in the system prompt. The first
version of that prompt gave a literal example chapter title and filled every character-id slot
of the JSON example with the same in-story character.

Playtest feedback was that the story kept drifting back to that character even after the player
had moved on to other storylines. The transcript showed the mechanism: the turn-1 chapter title
was the prompt's example title copied character-for-character, every later title reused its
opening character, and the example character kept reappearing in scenes about someone else.

This was not a JSON-format failure — the model produced correctly shaped output. It reused
**concrete content from the example** rather than treating the example as a description of the
shape to produce.

## Decision

In few-shot examples sent to small local models, replace named entities with placeholders
(`<角色id>` for character ids, `<旗標>` for flags) and add one line stating that they are
placeholders. Describe format-only conventions (the chapter-title couplet) in prose instead of
giving a literal example. The prompt also gained an explicit rule to follow the player's own
route rather than the source novel's chronology.

Because small models also copy their *own* earlier output, previous chapter titles are no longer
kept in the conversation history; the program tracks recent titles and asks for a new one when a
title repeats or is missing.

## Alternatives Considered

1. **Post-process and reject output mentioning the example's character.** Not chosen: it only
   catches the one name observed leaking and would also reject legitimate mentions.
2. **Use a larger GM model.** Not chosen: the engine is meant to run on the same resident 9B
   model as chat, and a larger model was not tested for this behaviour.

## Consequences

- In a single replay of the same 10-turn route after the change, the turn-1 title was no longer
  copied from the prompt, and mentions of the example character across three turns of an
  unrelated storyline dropped from 9 to 4. This is one sample, not a measured rate.
- The rule currently applies to `jpm_lib`'s prompt only; the wuxia engine's prompt was not changed.
- Transferable lesson: **at small-model scale, anything concrete in a few-shot example is a
  candidate for verbatim reuse.** Placeholders are cheap insurance against it.
