# Start Hermas monitoring stack (Prometheus + Grafana); skips anything already running.
# Usage: powershell -ExecutionPolicy Bypass -File D:\ai\monitoring\start-monitoring.ps1
# NOTE: keep this file ASCII-only (PowerShell 5.1 misreads BOM-less UTF-8 as ANSI).

$promDir = "D:\ai\monitoring\prometheus-3.13.0.windows-amd64"
$grafDir = "D:\ai\monitoring\grafana-13.1.0"

$prom = Get-Process prometheus -ErrorAction SilentlyContinue
if ($prom) {
    "Prometheus already running (PID=$($prom.Id))"
} else {
    Start-Process -FilePath "$promDir\prometheus.exe" `
        -ArgumentList "--config.file=D:\ai\monitoring\prometheus.yml", "--storage.tsdb.path=D:\ai\monitoring\prometheus-data", "--web.listen-address=127.0.0.1:9090" `
        -WorkingDirectory $promDir -WindowStyle Hidden
    "Prometheus started -> http://127.0.0.1:9090"
}

$graf = Get-Process grafana -ErrorAction SilentlyContinue
if ($graf) {
    "Grafana already running (PID=$($graf.Id))"
} else {
    Start-Process -FilePath "$grafDir\bin\grafana.exe" `
        -ArgumentList "server", "--config=$grafDir\conf\custom.ini", "--homepath=$grafDir" `
        -WorkingDirectory "$grafDir\bin" -WindowStyle Hidden
    "Grafana started -> http://127.0.0.1:3000 (first login: admin/admin)"
}
