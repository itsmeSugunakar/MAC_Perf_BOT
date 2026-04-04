#!/usr/bin/env python3
"""
macOS Performance Bot
Monitors system resources and throttles high-CPU processes to keep the Mac snappy.
"""

import os
import sys
import time
import signal
import logging
import subprocess
from datetime import datetime
from pathlib import Path

try:
    import psutil
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "psutil", "-q"], check=True)
    import psutil

# ── Config ──────────────────────────────────────────────────────────────────
LOG_DIR = Path.home() / "Library" / "Logs" / "performance-bot"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE       = LOG_DIR / "performance_bot.log"
CHECK_INTERVAL = 10          # seconds between checks
CPU_WARN       = 70.0        # % CPU (1-core equivalent) that triggers a warning
CPU_THROTTLE   = 85.0        # % CPU to renice the offending process
MEM_WARN       = 80.0        # % RAM usage to warn
RENICE_VALUE   = 10          # nice increment for throttled processes (lower = less priority)
MAX_LOG_MB     = 5           # rotate log after this many MB

# Processes we must never touch
PROTECTED = {
    "kernel_task", "launchd", "WindowServer", "loginwindow",
    "Finder", "Dock", "SystemUIServer", "coreaudiod", "cfprefsd",
    "mds", "mds_stores", "mdworker", "performance_bot",
}

# ── Logging ──────────────────────────────────────────────────────────────────
def setup_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(LOG_FILE),
            logging.StreamHandler(sys.stdout),
        ],
    )

# ── Notifications ─────────────────────────────────────────────────────────────
def notify(title: str, message: str):
    script = (
        f'display notification "{message}" with title "{title}" '
        f'sound name "Purr"'
    )
    subprocess.run(["osascript", "-e", script], capture_output=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def cpu_count() -> int:
    return psutil.cpu_count(logical=True) or 1


def process_cpu_percent(proc: psutil.Process) -> float:
    """Return per-core CPU % (0-100 per logical CPU)."""
    try:
        return proc.cpu_percent(interval=None) / cpu_count()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return 0.0


def renice(proc: psutil.Process):
    """Lower scheduling priority of a process."""
    try:
        current = proc.nice()
        if current < RENICE_VALUE:
            proc.nice(RENICE_VALUE)
            logging.info(
                "Reniced PID %d (%s): nice %d → %d",
                proc.pid, proc.name(), current, RENICE_VALUE,
            )
            return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
        pass
    return False


def restore_nice(proc: psutil.Process):
    """Restore normal priority if load has dropped."""
    try:
        if proc.nice() >= RENICE_VALUE:
            proc.nice(0)
    except (psutil.NoSuchProcess, psutil.AccessDenied, ProcessLookupError):
        pass


# ── Core monitor loop ─────────────────────────────────────────────────────────
class PerformanceBot:
    def __init__(self):
        self.throttled: set[int] = set()   # PIDs currently reniced
        self.running = True
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT,  self._shutdown)

        # Warm-up: first cpu_percent call always returns 0
        psutil.cpu_percent(interval=1)
        for p in psutil.process_iter(["cpu_percent"]):
            try:
                p.cpu_percent(interval=None)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    def _shutdown(self, *_):
        logging.info("Performance Bot shutting down.")
        self.running = False

    # ── Memory pressure ──────────────────────────────────────────────────────
    def check_memory(self):
        mem = psutil.virtual_memory()
        if mem.percent >= MEM_WARN:
            logging.warning(
                "High memory pressure: %.1f%% used (%.1f GB / %.1f GB)",
                mem.percent,
                (mem.total - mem.available) / 1e9,
                mem.total / 1e9,
            )
            notify(
                "Performance Bot – Memory",
                f"RAM at {mem.percent:.0f}% — consider closing unused apps.",
            )

    # ── CPU hogs ─────────────────────────────────────────────────────────────
    def check_cpu(self):
        system_cpu = psutil.cpu_percent(interval=None)

        if system_cpu < CPU_WARN:
            # Restore any previously throttled procs that have calmed down
            for pid in list(self.throttled):
                try:
                    p = psutil.Process(pid)
                    if process_cpu_percent(p) < CPU_WARN / 2:
                        restore_nice(p)
                        self.throttled.discard(pid)
                        logging.info("Restored priority for PID %d (%s)", pid, p.name())
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    self.throttled.discard(pid)
            return

        logging.info("System CPU at %.1f%% — scanning for hogs …", system_cpu)

        procs = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "nice"]):
            try:
                cpu = process_cpu_percent(p)
                if cpu >= CPU_WARN and p.name() not in PROTECTED:
                    procs.append((cpu, p))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        procs.sort(reverse=True, key=lambda x: x[0])

        for cpu, p in procs[:5]:          # cap how many we act on per cycle
            if cpu >= CPU_THROTTLE and p.pid not in self.throttled:
                if renice(p):
                    self.throttled.add(p.pid)
                    notify(
                        "Performance Bot – CPU",
                        f"{p.name()} (PID {p.pid}) using {cpu:.0f}% CPU — throttled.",
                    )
            elif cpu >= CPU_WARN:
                logging.warning(
                    "High CPU: %-30s  PID %-7d  %.1f%%",
                    p.name(), p.pid, cpu,
                )

    # ── Disk / swap sanity ───────────────────────────────────────────────────
    def check_disk(self):
        try:
            disk = psutil.disk_usage("/")
            if disk.percent >= 90:
                logging.warning(
                    "Low disk space: %.0f%% used (%.1f GB free)",
                    disk.percent,
                    disk.free / 1e9,
                )
                notify(
                    "Performance Bot – Disk",
                    f"Boot volume {disk.percent:.0f}% full — free some space!",
                )
        except Exception:
            pass

        swap = psutil.swap_memory()
        if swap.total > 0 and swap.percent >= 50:
            logging.warning(
                "Swap usage at %.1f%% (%.1f GB used)",
                swap.percent, swap.used / 1e9,
            )

    # ── Top-process report (every ~5 min) ───────────────────────────────────
    def report_top(self):
        rows = []
        for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            try:
                rows.append((
                    process_cpu_percent(p),
                    p.memory_percent(),
                    p.pid,
                    p.name(),
                ))
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        rows.sort(reverse=True)
        top = rows[:8]
        lines = ["─── Top processes ───────────────────────────────────────"]
        lines.append(f"  {'Name':<35} {'PID':>7}  {'CPU%':>6}  {'MEM%':>6}")
        for cpu, mem, pid, name in top:
            lines.append(f"  {name:<35} {pid:>7}  {cpu:>5.1f}%  {mem:>5.1f}%")
        logging.info("\n".join(lines))

    # ── Main loop ─────────────────────────────────────────────────────────────
    def run(self):
        logging.info(
            "Performance Bot started (PID %d) — checking every %ds",
            os.getpid(), CHECK_INTERVAL,
        )
        notify("Performance Bot", "Started — monitoring system performance.")

        tick = 0
        while self.running:
            try:
                self.check_cpu()
                if tick % 3 == 0:        # every 3 × CHECK_INTERVAL ≈ 30 s
                    self.check_memory()
                    self.check_disk()
                if tick % 30 == 0:       # every 30 × CHECK_INTERVAL ≈ 5 min
                    self.report_top()
            except Exception as exc:
                logging.exception("Unexpected error: %s", exc)

            tick += 1
            time.sleep(CHECK_INTERVAL)

        logging.info("Performance Bot stopped.")


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    setup_logging()
    PerformanceBot().run()
