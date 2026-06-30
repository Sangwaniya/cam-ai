import time
import threading

# GPU telemetry (optional). Falls back to CPU-based control if unavailable.
try:
    import pynvml
    pynvml.nvmlInit()
    _GPU_HANDLE = pynvml.nvmlDeviceGetHandleByIndex(0)
    GPU_AVAILABLE = True
except Exception:
    GPU_AVAILABLE = False
    _GPU_HANDLE = None

try:
    import psutil
    _HAS_PSUTIL = True
except Exception:
    _HAS_PSUTIL = False


class BatchScheduler:
    """
    Adaptive, load-aware, priority GPU-slot scheduler for the Tier-2 scanner.
    See docs/PRIORITY_AND_LOAD.md for the full write-up. Summary:

      * Each frame with motion, a stream calls request(stream_id, priority).
      * Slots are granted to the top `effective_slots` streams by priority.
      * `effective_slots` is NOT fixed: a background sampler reads GPU (or, if no
        GPU, CPU) load and adjusts it - shrinking under high load, growing under
        low load, bounded by [min_slots, max_slots]. So prioritisation only
        "bites" when the hardware is genuinely saturated, or when demand exceeds
        the hard ceiling (max_slots).
      * Demand expires after `demand_ttl`s, so a camera that stops moving frees
        its place automatically.
    """
    def __init__(self, max_slots=4, min_slots=1, gpu_high=85, gpu_low=60,
                 cpu_high=90, cpu_low=70, demand_ttl=1.0, sample_interval=1.0,
                 autostart_sampler=True):
        self.max_slots = max_slots
        self.min_slots = min_slots
        self.gpu_high = gpu_high
        self.gpu_low = gpu_low
        self.cpu_high = cpu_high
        self.cpu_low = cpu_low
        self.demand_ttl = demand_ttl
        self.sample_interval = sample_interval

        self.effective_slots = max_slots   # start optimistic; controller adjusts
        self.gpu_util = None
        self.gpu_mem = None
        self.cpu = 0.0
        self.demand = {}                   # stream_id -> (priority, last_seen_ts)
        self.lock = threading.Lock()

        self._stop = threading.Event()
        self._sampler = None
        if autostart_sampler:
            self._sampler = threading.Thread(target=self._sample_loop, daemon=True)
            self._sampler.start()

    @staticmethod
    def _read_load():
        gpu_util = gpu_mem = None
        if GPU_AVAILABLE:
            try:
                rates = pynvml.nvmlDeviceGetUtilizationRates(_GPU_HANDLE)
                gpu_util = int(rates.gpu)
                mem = pynvml.nvmlDeviceGetMemoryInfo(_GPU_HANDLE)
                gpu_mem = int(round(100 * mem.used / mem.total))
            except Exception:
                pass
        cpu = psutil.cpu_percent() if _HAS_PSUTIL else None
        return gpu_util, gpu_mem, cpu

    def _apply_load(self, gpu_util, gpu_mem, cpu):
        """Adjust effective_slots from the governing load signal (pure + testable)."""
        with self.lock:
            self.gpu_util, self.gpu_mem = gpu_util, gpu_mem
            if cpu is not None:
                self.cpu = cpu
            load = gpu_util if gpu_util is not None else cpu
            high = self.gpu_high if gpu_util is not None else self.cpu_high
            low = self.gpu_low if gpu_util is not None else self.cpu_low
            if load is None:
                return
            if load > high:                # saturated -> shed a stream
                self.effective_slots = max(self.min_slots, self.effective_slots - 1)
            elif load < low:               # headroom -> admit a stream
                self.effective_slots = min(self.max_slots, self.effective_slots + 1)
            # in the hysteresis band [low, high] -> hold steady

    def _sample_loop(self):
        if _HAS_PSUTIL:
            try:
                psutil.cpu_percent()  # prime the first reading
            except Exception:
                pass
        while not self._stop.is_set():
            self._apply_load(*self._read_load())
            time.sleep(self.sample_interval)

    def request(self, stream_id, priority=0, now=None) -> bool:
        """Register/refresh demand; True if this stream may use a slot this frame."""
        now = time.time() if now is None else now
        with self.lock:
            self.demand[stream_id] = (priority, now)
            self.demand = {s: (p, t) for s, (p, t) in self.demand.items()
                           if now - t < self.demand_ttl}
            ranked = sorted(self.demand.items(), key=lambda kv: (-kv[1][0], kv[0]))
            allowed = [s for s, _ in ranked[:self.effective_slots]]
            return stream_id in allowed

    def stats(self, now=None):
        now = time.time() if now is None else now
        with self.lock:
            active = sum(1 for _, (_, t) in self.demand.items() if now - t < self.demand_ttl)
            return {
                "gpu_available": GPU_AVAILABLE,
                "gpu_util": self.gpu_util,
                "gpu_mem": self.gpu_mem,
                "cpu": int(round(self.cpu)) if self.cpu is not None else None,
                "governing": "gpu" if self.gpu_util is not None else "cpu",
                "effective_slots": self.effective_slots,
                "max_slots": self.max_slots,
                "min_slots": self.min_slots,
                "active_streams": active,
                "contention": active > self.effective_slots,
            }

    def shutdown(self):
        self._stop.set()

    # --- backwards-compatible shims (old API) ---
    def acquire_slot(self, stream_id, priority=0) -> bool:
        return self.request(stream_id, priority)

    def release_slot(self, stream_id):
        pass
