# Operations

## Runbook

| Concern | Current practice |
|---|---|
| Startup order | the bot detects and auto-starts ComfyUI as a child process if it is not already running (90 s readiness wait, terminated on bot exit); manual pre-start also supported |
| Process supervision | manual / console; bot restart clears per-channel chat history (by design — long-term memory lives in the vector store) |
| Configuration | `.env` via `python-dotenv`; every variable has a code default; secrets never in code or logs |
| Deploy check | syntax gate (`py_compile`) → restart → verify Discord login event fires |
| Encoding | `PYTHONUTF8=1` is mandatory on Windows consoles (cp950 cannot print emoji output) |

## Failure Modes & Handling

| Failure | Blast radius | Handling |
|---|---|---|
| ComfyUI down | image commands only | submit/monitor/fetch each wrapped; user gets an actionable error, chat unaffected |
| Ollama down | chat, RPG, expansion tier 1 | chat/RPG report the failure; expansion falls through to cloud tiers (ADR-0003) |
| OpenRouter unavailable / no key | none visible | tiers skipped; chain continues to local fallback |
| Claude API unavailable / no key (tarot) | tarot reading quality only | falls back to a local rule-based reading; card draw and image lookup are unaffected |
| LLM omits required JSON (RPG engines) | one game turn | targeted re-ask for the missing JSON block; if it still fails, the narration is delivered and that turn's state changes are dropped |
| Transient Ollama connection error (RPG engines) | one call | single automatic retry before surfacing |
| Concurrent GPU commands | queueing latency | an in-process reentrant lock covers model eviction and inference; cloud RPG fallback acquires it only when entering local inference; the adult RPG engine's turn and media generation acquire the same lock through separate named guard groups |
| Concurrent state changes | RPG save loss / overlapping quizzes | reject overlapping operations per channel (RPG/adult RPG/chat) or per user and channel (quiz); retain guard until work completes even if its caller cancels |
| Non-age-restricted channel (adult RPG) | that command only | every command and button re-checks `channel.is_nsfw()`; rejected outright, no partial state created |

## Monitoring

The design intent is that *degradation should be visible before users report it*. The bot
process exports Prometheus metrics (`prometheus_client` HTTP exporter, `METRICS_PORT`,
default 9109); a metrics module degrades to no-ops if the client library is absent, so
monitoring can never take the bot down. GPU state is sampled every 10 s via NVML plus
Ollama's `/api/ps`. Prometheus and Grafana run as local processes with a provisioned
dashboard (GPU arbitration, pipeline health — six panels).

| Metric | Type | Why it matters |
|---|---|---|
| `hermas_gpu_vram_used_bytes` / `_total_bytes` | gauge | verifies the arbitration invariant (ADR-0001) actually holds |
| `hermas_ollama_model_vram_bytes{model}` | gauge | which models are resident — makes the keep-alive policy (ADR-0002) visible |
| `hermas_ollama_sample_up` | gauge | latest sample success; failed samples invalidate model VRAM values with NaN |
| `hermas_expansion_tier_total{tier}` | counter | drift toward lower tiers = tier 1 silently unhealthy (ADR-0003) |
| `hermas_image_duration_seconds` | histogram | render latency incl. eviction cost; regression alarm |
| `hermas_vram_eviction_total{direction}` | counter | arbitration activity in both directions (ADR-0001) |
| `hermas_command_errors_total{command}` | counter | user-visible failure rate per feature |

## Known Limitations

Stated plainly, because the scale assumptions are part of the architecture:

1. **In-process GPU arbitration.** The bot serializes its GPU consumers, but external
   ComfyUI clients and other applications do not share this lock. Avoid running heavy
   external GPU jobs alongside the bot.
2. **Single-host, single-GPU, no HA.** A host reboot takes everything down. Accepted: this
   is a personal platform, not a service with an SLO.
3. **Chat short-term memory is process-local.** Restart loses the last 20 messages per
   channel. Mitigated by vector-store long-term memory; accepted otherwise.
4. **Free cloud fallback tiers are unstable by nature.** Models get delisted or throttled
   without notice; the chain tolerates it, monitoring will make it visible.
5. **Memory ingestion is incremental and single-worker.** Each new transcript is submitted
   once. Failed ingestion leaves the source file intact and reports a warning; automatic
   replay after process termination is not implemented.

## Local validation (2026-09-18)

`research/test_runtime_coordination.py` covers GPU serialization, RPG cloud fallback,
state guards, cancellation, incremental ingestion, cached image completion and stale
metrics. `research/validate_local_upgrade.py` runs actual image, ControlNet, video,
chat, RPG and LM Studio API checks without writing production game saves or memories.
`start-bot.ps1` launches the bot with explicit ComfyUI 0.36.0 paths and UTF-8 logging.
