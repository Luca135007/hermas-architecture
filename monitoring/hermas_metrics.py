"""Hermas Prometheus 監控模組（Phase B 可觀測性）。

獨立模組，供 bot.py 以最小侵入方式掛儀表點。
prometheus_client 或 pynvml 缺少任一者時，全部公開函式退化為 no-op，
確保監控功能損壞不影響 bot 主流程（比照 bot.py 對 dotenv 的防護風格）。
"""

import json
import os
import threading
import time
import urllib.request

try:
    from prometheus_client import start_http_server, Gauge, Counter, Histogram
    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False

try:
    import pynvml
    _NVML_AVAILABLE = True
except ImportError:
    _NVML_AVAILABLE = False

METRICS_PORT = int(os.getenv("METRICS_PORT", "9109"))
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "127.0.0.1:11434")

_SAMPLE_INTERVAL_SECONDS = 10
_GPU_INDEX = 0

_started = False
_last_ollama_models = set()  # 上一輪有回報 VRAM 的模型名稱，用來把這輪消失的模型歸零

if _PROM_AVAILABLE:
    GPU_VRAM_USED_BYTES = Gauge(
        "hermas_gpu_vram_used_bytes", "GPU 已使用 VRAM（位元組）"
    )
    GPU_VRAM_TOTAL_BYTES = Gauge(
        "hermas_gpu_vram_total_bytes", "GPU 總 VRAM 容量（位元組）"
    )
    OLLAMA_MODEL_VRAM_BYTES = Gauge(
        "hermas_ollama_model_vram_bytes", "Ollama 各模型佔用 VRAM（位元組）", ["model"]
    )
    EXPANSION_TIER_TOTAL = Counter(
        "hermas_expansion_tier_total", "提示詞擴寫成功次數，依服務層級分類", ["tier"]
    )
    IMAGE_DURATION_SECONDS = Histogram(
        "hermas_image_duration_seconds", "生圖工作流程整體耗時（秒）",
        buckets=(5, 10, 20, 30, 60, 90, 120, 180, 300)
    )
    VRAM_EVICTION_TOTAL = Counter(
        "hermas_vram_eviction_total", "VRAM 讓位次數，依方向分類", ["direction"]
    )
    COMMAND_ERRORS_TOTAL = Counter(
        "hermas_command_errors_total", "使用者可見錯誤次數，依指令分類", ["command"]
    )


def _sample_gpu_vram():
    """每輪取樣 NVML GPU 0 的 VRAM 使用量與總量"""
    if not _NVML_AVAILABLE:
        return
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(_GPU_INDEX)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        GPU_VRAM_USED_BYTES.set(mem.used)
        GPU_VRAM_TOTAL_BYTES.set(mem.total)
    except Exception:
        pass  # 監控失敗不得影響主流程


def _sample_ollama_vram():
    """每輪取樣 Ollama /api/ps，把上輪有這輪沒有的模型歸零"""
    global _last_ollama_models
    try:
        with urllib.request.urlopen(f"http://{OLLAMA_HOST}/api/ps", timeout=5) as resp:
            data = json.loads(resp.read())
        models = data.get("models", [])
        current_models = set()
        for m in models:
            name = m.get("name", "")
            if not name:
                continue
            OLLAMA_MODEL_VRAM_BYTES.labels(model=name).set(m.get("size_vram", 0))
            current_models.add(name)
        for stale in _last_ollama_models - current_models:
            OLLAMA_MODEL_VRAM_BYTES.labels(model=stale).set(0)
        _last_ollama_models = current_models
    except Exception:
        pass  # Ollama 沒開或連不上時不影響主流程


def _sample_loop():
    if _NVML_AVAILABLE:
        try:
            pynvml.nvmlInit()
        except Exception:
            pass
    while True:
        _sample_gpu_vram()
        _sample_ollama_vram()
        time.sleep(_SAMPLE_INTERVAL_SECONDS)


def start_metrics(port: int = None):
    """啟動 Prometheus HTTP 伺服器與背景取樣執行緒；缺套件時直接 no-op"""
    global _started
    if not _PROM_AVAILABLE or _started:
        return
    try:
        start_http_server(port or METRICS_PORT)
        threading.Thread(target=_sample_loop, daemon=True).start()
        _started = True
    except Exception as e:
        print(f"[Metrics] ⚠️ 啟動失敗（不影響流程）：{e}")


def observe_image_duration(seconds: float):
    """生圖工作流程成功時記錄整體耗時"""
    if not _PROM_AVAILABLE:
        return
    IMAGE_DURATION_SECONDS.observe(seconds)


def record_expansion_tier(tier: str):
    """擴寫成功時記錄使用的服務層級（模型識別字）"""
    if not _PROM_AVAILABLE:
        return
    EXPANSION_TIER_TOTAL.labels(tier=tier).inc()


def record_eviction(direction: str):
    """VRAM 讓位成功時記錄方向（"llm" 或 "image"）"""
    if not _PROM_AVAILABLE:
        return
    VRAM_EVICTION_TOTAL.labels(direction=direction).inc()


def record_command_error(command: str):
    """使用者可見錯誤發生時記錄指令名"""
    if not _PROM_AVAILABLE:
        return
    COMMAND_ERRORS_TOTAL.labels(command=command).inc()
