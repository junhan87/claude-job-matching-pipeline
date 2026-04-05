"""StatsCollector — tracks wall-clock time and Anthropic token usage across pipeline phases."""

import time
import threading
from collections import defaultdict
from core.config import MODEL_NAME

# Public pricing for MODEL_NAME (USD per million tokens)
# 5-min cache write = 1.25x input; 1-hour cache write = 2.00x input (not distinguished here)
_PRICE = {
    'input':         1.00,
    'output':        5.00,
    'cache_read':    0.10,
    'cache_write':   1.25,
}


class StatsCollector:
    def __init__(self):
        # timing: label -> {'calls': int, 'total_s': float}
        self._timing: dict[str, dict] = defaultdict(lambda: {'calls': 0, 'total_s': 0.0})
        self._local = threading.local()   # per-thread start timestamps (avoids cross-thread clobbering)
        self._lock  = threading.Lock()    # guards _timing and _tokens mutations
        # tokens: label -> {'input': int, 'output': int, 'cache_read': int, 'cache_write': int, 'calls': int}
        self._tokens: dict[str, dict] = defaultdict(
            lambda: {'calls': 0, 'input': 0, 'output': 0, 'cache_read': 0, 'cache_write': 0}
        )

    # ------------------------------------------------------------------
    # Timing API
    # ------------------------------------------------------------------

    def start(self, label: str) -> None:
        if not hasattr(self._local, 'starts'):
            self._local.starts = {}
        self._local.starts[label] = time.perf_counter()

    def stop(self, label: str) -> float:
        if not hasattr(self._local, 'starts'):
            self._local.starts = {}
        elapsed = time.perf_counter() - self._local.starts.pop(label, time.perf_counter())
        with self._lock:
            self._timing[label]['calls'] += 1
            self._timing[label]['total_s'] += elapsed
        return elapsed

    # ------------------------------------------------------------------
    # Token tracking API
    # ------------------------------------------------------------------

    def record_usage(self, response, label: str) -> None:
        """Extract usage from an Anthropic response object and accumulate."""
        usage = getattr(response, 'usage', None)
        if usage is None:
            return
        with self._lock:
            bucket = self._tokens[label]
            bucket['calls'] += 1
            bucket['input']       += getattr(usage, 'input_tokens', 0)
            bucket['output']      += getattr(usage, 'output_tokens', 0)
            bucket['cache_read']  += getattr(usage, 'cache_read_input_tokens', 0)
            bucket['cache_write'] += getattr(usage, 'cache_creation_input_tokens', 0)

    # ------------------------------------------------------------------
    # Summary output
    # ------------------------------------------------------------------

    def summary(self) -> None:
        self._print_timing()
        self._print_tokens()

    def _print_timing(self) -> None:
        if not self._timing:
            return
        rows = sorted(self._timing.items(), key=lambda kv: -kv[1]['total_s'])
        label_w = max(len(k) for k, _ in rows)
        print("\n" + "=" * 60)
        print("  TIMING SUMMARY")
        print("=" * 60)
        header = f"  {'Phase':<{label_w}}  {'Calls':>5}  {'Total':>8}  {'Avg':>8}"
        print(header)
        print(f"  {'-' * label_w}  {'-' * 5}  {'-' * 8}  {'-' * 8}")
        for label, v in rows:
            calls = v['calls']
            total = v['total_s']
            avg   = total / calls if calls else 0.0
            print(f"  {label:<{label_w}}  {calls:>5}  {total:>7.2f}s  {avg:>7.2f}s")

    def _print_tokens(self) -> None:
        if not self._tokens:
            return
        rows = sorted(self._tokens.items(), key=lambda kv: -(kv[1]['input'] + kv[1]['output']))
        label_w = max(len(k) for k, _ in rows)

        # Totals row
        total_input  = sum(v['input']       for v in self._tokens.values())
        total_output = sum(v['output']      for v in self._tokens.values())
        total_cr     = sum(v['cache_read']  for v in self._tokens.values())
        total_cw     = sum(v['cache_write'] for v in self._tokens.values())
        total_cost   = self._cost(total_input, total_output, total_cr, total_cw)

        print("\n" + "=" * 60)
        print(f"  TOKEN USAGE SUMMARY  ({MODEL_NAME})")
        print("=" * 60)
        header = (
            f"  {'Phase':<{label_w}}  {'Calls':>5}  "
            f"{'Input':>8}  {'Output':>7}  {'CacheR':>7}  {'CacheW':>7}  {'Cost$':>8}"
        )
        print(header)
        print(f"  {'-' * label_w}  {'-' * 5}  {'-' * 8}  {'-' * 7}  {'-' * 7}  {'-' * 7}  {'-' * 8}")
        for label, v in rows:
            cost = self._cost(v['input'], v['output'], v['cache_read'], v['cache_write'])
            print(
                f"  {label:<{label_w}}  {v['calls']:>5}  "
                f"{v['input']:>8,}  {v['output']:>7,}  "
                f"{v['cache_read']:>7,}  {v['cache_write']:>7,}  {cost:>8.4f}"
            )
        print(f"  {'TOTAL':<{label_w}}  {'':>5}  "
              f"{total_input:>8,}  {total_output:>7,}  "
              f"{total_cr:>7,}  {total_cw:>7,}  {total_cost:>8.4f}")

    @staticmethod
    def _cost(inp: int, out: int, cache_read: int, cache_write: int) -> float:
        return (
            inp        * _PRICE['input']       / 1_000_000
            + out      * _PRICE['output']      / 1_000_000
            + cache_read  * _PRICE['cache_read']  / 1_000_000
            + cache_write * _PRICE['cache_write'] / 1_000_000
        )


# Module-level singleton — import this everywhere
stats = StatsCollector()
