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
| LLM omits required JSON (RPG) | one game turn | targeted re-ask for the missing JSON block; if it still fails, the narration is delivered and that turn's state changes are dropped |
| Transient Ollama connection error (RPG) | one call | single automatic retry before surfacing |
| Concurrent GPU commands | latency, possible thrash | accepted at current scale — see Known Limitations |

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
| `hermas_expansion_tier_total{tier}` | counter | drift toward lower tiers = tier 1 silently unhealthy (ADR-0003) |
| `hermas_image_duration_seconds` | histogram | render latency incl. eviction cost; regression alarm |
| `hermas_vram_eviction_total{direction}` | counter | arbitration activity in both directions (ADR-0001) |
| `hermas_command_errors_total{command}` | counter | user-visible failure rate per feature |

## Known Limitations

Stated plainly, because the scale assumptions are part of the architecture:

1. **Convention-based GPU arbitration.** No lock or queue serializes GPU consumers; two
   simultaneous commands can interleave evictions and thrash. Acceptable for one small
   community; the documented upgrade path is a broker with a queue (ADR-0001, alt. 4).
2. **Single-host, single-GPU, no HA.** A host reboot takes everything down. Accepted: this
   is a personal platform, not a service with an SLO.
3. **Chat short-term memory is process-local.** Restart loses the last 20 messages per
   channel. Mitigated by vector-store long-term memory; accepted otherwise.
4. **Free cloud fallback tiers are unstable by nature.** Models get delisted or throttled
   without notice; the chain tolerates it, monitoring will make it visible.
5. **No automated tests around the arbitration path.** Verification is currently behavioral
   (deploy check + real usage). Highest-value next engineering investment alongside Phase B.
