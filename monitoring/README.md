# Monitoring — Reference Implementation

The Phase B monitoring stack described in [../docs/operations.md](../docs/operations.md),
as deployed:

- **`hermas_metrics.py`** — the exporter module loaded by the bot (snapshot). Import-guarded:
  if `prometheus_client` or `pynvml` is missing, every public function degrades to a no-op,
  so monitoring can never take the bot down. A daemon thread samples NVML (GPU 0) and
  Ollama `/api/ps` every 10 seconds.
- **`prometheus.yml`** — scrape config (bot exporter on `:9109`, 10 s interval).
- **`grafana-provisioning/`** — datasource and dashboard provisioned as code; the dashboard
  (six panels) maps each metric back to the ADR whose invariant it verifies.
- **`start-monitoring.ps1`** — starts Prometheus and Grafana as local processes on Windows;
  idempotent.

Design choice: native binaries instead of Docker Desktop — the monitoring stack must be
cheap enough to run 24/7 next to a GPU workload, and a WSL2 VM is not.
