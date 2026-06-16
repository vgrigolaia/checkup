#!/usr/bin/env python3
"""
checkup — Lightweight Network Uptime Monitor
Zero external dependencies. Python 3.6+ standard library only.
https://github.com/vgrigolaia/checkup
"""

import argparse
import json
import os
import re
import signal
import subprocess
import sys
import time
from datetime import datetime

__version__ = "1.0.0"


# ---------------------------------------------------------------------------
# Terminal colors (ANSI) — disabled automatically when not a TTY
# ---------------------------------------------------------------------------

class _Color:
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"

_USE_COLOR = sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    """Wrap text in an ANSI code (no-op when color is disabled)."""
    return f"{code}{text}{_Color.RESET}" if _USE_COLOR else text


def _strip_ansi(text: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", text)


# ---------------------------------------------------------------------------
# Core monitor class
# ---------------------------------------------------------------------------

class CheckupMonitor:
    def __init__(
        self,
        target: str,
        interval: float = 2.0,
        log_file: str = None,
        json_report: str = None,
        quiet: bool = False,
    ):
        self.target      = target
        self.interval    = interval
        self.log_file    = log_file
        self.json_report = json_report
        self.quiet       = quiet

        self.session_start   = datetime.now()
        self.is_up           = None          # None = not yet checked
        self.downtime_start  = None
        self.downtime_events = []

        self.ping_count   = 0
        self.ping_success = 0
        self.rtt_samples  = []

        self._on_live_line = False  # cursor is on an overwrite-able live line
        self._running      = True

        signal.signal(signal.SIGINT,  self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _write_file(self, plain_line: str) -> None:
        if not self.log_file:
            return
        try:
            with open(self.log_file, "a") as fh:
                fh.write(plain_line + "\n")
        except IOError as exc:
            print(f"Warning: cannot write to log file: {exc}", file=sys.stderr)

    def _newline_if_live(self) -> None:
        """Move past a live-updating line before printing a permanent line."""
        if self._on_live_line:
            print()
            self._on_live_line = False

    def log(self, message: str, raw: bool = False) -> None:
        """Print a timestamped line to stdout and to the log file."""
        self._newline_if_live()
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = message if raw else f"[{ts}] {message}"
        print(line)
        self._write_file(_strip_ansi(line))

    def _live(self, message: str) -> None:
        """Overwrite the current terminal line (status ticker)."""
        if self.quiet:
            return
        print(f"\r  {message}   ", end="", flush=True)
        self._on_live_line = True

    def _separator(self, char: str = "-", width: int = 60) -> None:
        self.log(_c(_Color.DIM, char * width), raw=True)

    # ------------------------------------------------------------------
    # Ping
    # ------------------------------------------------------------------

    def _ping(self) -> "tuple[bool, float | None]":
        """
        Send a single ICMP ping.
        Returns (reachable, rtt_ms).  rtt_ms is None if not available.
        """
        try:
            proc = subprocess.run(
                ["ping", "-c", "1", "-W", "2", self.target],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5,
            )
            if proc.returncode == 0:
                m = re.search(r"time[=<]([\d.]+)\s*ms", proc.stdout.decode())
                rtt = float(m.group(1)) if m else None
                return True, rtt
            return False, None
        except subprocess.TimeoutExpired:
            return False, None
        except FileNotFoundError:
            sys.exit(_c(_Color.RED, "Error: 'ping' command not found on this system."))
        except Exception:
            return False, None

    # ------------------------------------------------------------------
    # Duration formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _fmt(seconds: float, short: bool = False) -> str:
        s = int(seconds)
        if s < 60:
            return f"{s}s" if short else f"{s} seconds"
        m, s = divmod(s, 60)
        if m < 60:
            if short:
                return f"{m}m {s}s"
            return f"{m} {'minute' if m == 1 else 'minutes'}, {s} seconds"
        h, m = divmod(m, 60)
        if short:
            return f"{h}h {m}m {s}s"
        return f"{h} {'hour' if h == 1 else 'hours'}, {m} {'minute' if m == 1 else 'minutes'}, {s} seconds"

    # ------------------------------------------------------------------
    # Header / summary
    # ------------------------------------------------------------------

    def _print_header(self) -> None:
        w = 60
        print()
        print(_c(_Color.BOLD + _Color.CYAN,  "=" * w))
        print(_c(_Color.BOLD + _Color.WHITE, "  checkup  —  Network Uptime Monitor"))
        print(_c(_Color.BOLD + _Color.CYAN,  "=" * w))
        ts = self.session_start.strftime("%Y-%m-%d %H:%M:%S")
        self.log(f"  Session Started : {_c(_Color.WHITE, ts)}")
        self.log(f"  Target          : {_c(_Color.WHITE, self.target)}")
        self.log(f"  Ping Interval   : {_c(_Color.WHITE, str(self.interval) + 's')}")
        if self.log_file:
            self.log(f"  Log File        : {_c(_Color.WHITE, self.log_file)}")
        if self.json_report:
            self.log(f"  JSON Report     : {_c(_Color.WHITE, self.json_report)}")
        print(_c(_Color.BOLD + _Color.CYAN, "-" * w))
        print()

    def _print_summary(self) -> None:
        now          = datetime.now()
        session_secs = (now - self.session_start).total_seconds()
        loss_pct     = (
            (self.ping_count - self.ping_success) / self.ping_count * 100
            if self.ping_count else 0.0
        )
        avg_rtt = sum(self.rtt_samples) / len(self.rtt_samples) if self.rtt_samples else None

        print()
        print(_c(_Color.BOLD + _Color.CYAN,  "=" * 60))
        print(_c(_Color.BOLD + _Color.WHITE, "  SESSION SUMMARY"))
        print(_c(_Color.BOLD + _Color.CYAN,  "=" * 60))

        self.log(f"  Ended           : {now.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"  Session Duration: {self._fmt(session_secs)}")
        self.log(f"  Pings Sent      : {self.ping_count}")
        self.log(f"  Packet Loss     : {loss_pct:.1f}%")

        if avg_rtt is not None:
            mn = min(self.rtt_samples)
            mx = max(self.rtt_samples)
            self.log(
                f"  RTT min/avg/max : "
                f"{mn:.1f} / {avg_rtt:.1f} / {mx:.1f} ms"
            )

        print()

        if not self.downtime_events:
            self.log(
                _c(_Color.GREEN + _Color.BOLD,
                   "  Status: No downtime detected — target was UP the entire session.")
            )
        else:
            total_down = sum(e["duration"] for e in self.downtime_events)
            self.log(_c(_Color.YELLOW, f"  Downtime Events : {len(self.downtime_events)}"))
            self.log(_c(_Color.YELLOW, f"  Total Downtime  : {self._fmt(total_down)}"))
            print()
            print(_c(_Color.BOLD, "  Incident Log"))
            print(_c(_Color.DIM,  "  " + "-" * 56))

            for idx, ev in enumerate(self.downtime_events, 1):
                lost_str     = ev["lost_at"].strftime("%Y-%m-%d %H:%M:%S")
                restored_str = ev["restored_at"].strftime("%Y-%m-%d %H:%M:%S")
                dur_str      = self._fmt(ev["duration"])
                print()
                self.log(f"  [{idx}] LOST     : {_c(_Color.RED,    lost_str)}")
                self.log(f"      RESTORED : {_c(_Color.GREEN,  restored_str)}")
                self.log(f"      Duration : {_c(_Color.YELLOW, dur_str)}")

        print()
        print(_c(_Color.BOLD + _Color.CYAN, "=" * 60))
        print()

        if self.json_report:
            self._write_json(session_secs, loss_pct, avg_rtt, now)

    def _write_json(
        self,
        session_secs: float,
        loss_pct: float,
        avg_rtt: "float | None",
        ended: datetime,
    ) -> None:
        report = {
            "session_start":           self.session_start.strftime("%Y-%m-%d %H:%M:%S"),
            "session_end":             ended.strftime("%Y-%m-%d %H:%M:%S"),
            "target":                  self.target,
            "interval_seconds":        self.interval,
            "session_duration_seconds": int(session_secs),
            "pings_sent":              self.ping_count,
            "pings_success":           self.ping_success,
            "packet_loss_pct":         round(loss_pct, 2),
            "rtt_ms": {
                "min": round(min(self.rtt_samples), 2) if self.rtt_samples else None,
                "avg": round(avg_rtt, 2)               if avg_rtt         else None,
                "max": round(max(self.rtt_samples), 2) if self.rtt_samples else None,
            },
            "downtime_events":         len(self.downtime_events),
            "total_downtime_seconds":  int(sum(e["duration"] for e in self.downtime_events)),
            "incidents": [
                {
                    "lost_at":          e["lost_at"].strftime("%Y-%m-%d %H:%M:%S"),
                    "restored_at":      e["restored_at"].strftime("%Y-%m-%d %H:%M:%S"),
                    "duration_seconds": int(e["duration"]),
                }
                for e in self.downtime_events
            ],
        }
        try:
            with open(self.json_report, "w") as fh:
                json.dump(report, fh, indent=2)
            self.log(f"[INFO] JSON report saved → {self.json_report}")
        except IOError as exc:
            print(f"Warning: cannot write JSON report: {exc}", file=sys.stderr)

    # ------------------------------------------------------------------
    # Signal handler
    # ------------------------------------------------------------------

    def _handle_shutdown(self, _sig, _frame) -> None:
        self._running = False
        self._newline_if_live()
        print()
        self.log(_c(_Color.DIM, "[INFO] Monitoring stopped by user (Ctrl+C)"))
        self._print_summary()
        sys.exit(0)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._print_header()

        while self._running:
            is_up, rtt = self._ping()
            now = datetime.now()

            self.ping_count += 1
            if is_up:
                self.ping_success += 1
                if rtt is not None:
                    self.rtt_samples.append(rtt)

            rtt_str = f"  RTT {rtt:.1f} ms" if (is_up and rtt is not None) else ""

            # ── First check: establish baseline ──────────────────────
            if self.is_up is None:
                status = _c(_Color.GREEN + _Color.BOLD, "UP") if is_up else _c(_Color.RED + _Color.BOLD, "DOWN")
                self.log(f"[INFO]  Initial status: {status}{rtt_str}")

            # ── UP → DOWN ────────────────────────────────────────────
            elif self.is_up and not is_up:
                self.downtime_start = now
                print()  # end any live line
                self._on_live_line = False
                self._separator("─")
                self.log(
                    _c(_Color.RED + _Color.BOLD,
                       f"[ALERT] Connection LOST at: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                )
                self._separator("─")

            # ── DOWN → UP ────────────────────────────────────────────
            elif not self.is_up and is_up:
                duration = (now - self.downtime_start).total_seconds()
                self._separator("─")
                self.log(
                    _c(_Color.GREEN + _Color.BOLD,
                       f"[INFO]    Connection RESTORED at: {now.strftime('%Y-%m-%d %H:%M:%S')}")
                )
                self.log(
                    _c(_Color.YELLOW,
                       f"[SUMMARY] Total Downtime Duration: {self._fmt(duration)}")
                )
                self._separator("─")
                print()
                self.downtime_events.append({
                    "lost_at":     self.downtime_start,
                    "restored_at": now,
                    "duration":    duration,
                })

            # ── Steady UP: live ticker ────────────────────────────────
            elif self.is_up and is_up:
                self._live(
                    _c(_Color.GREEN, "●") +
                    f"  {now.strftime('%H:%M:%S')}{rtt_str}"
                )

            # ── Steady DOWN: live "still down" counter ────────────────
            elif not self.is_up and not is_up:
                elapsed = (now - self.downtime_start).total_seconds()
                self._live(
                    _c(_Color.RED, "●") +
                    f"  {now.strftime('%H:%M:%S')}  still DOWN — {self._fmt(elapsed, short=True)}"
                )

            self.is_up = is_up
            time.sleep(self.interval)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="checkup",
        description=(
            "Lightweight network uptime monitor.\n"
            "Zero external dependencies — Python 3.6+ standard library only."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  checkup.py 8.8.8.8
  checkup.py google.com --interval 1
  checkup.py 192.168.1.1 --interval 2 --log uptime.log
  checkup.py 10.0.0.1 --interval 1 --log uptime.log --json-report report.json
  checkup.py 8.8.8.8 --no-color > uptime.txt
        """,
    )
    p.add_argument("target", help="IP address or hostname to monitor")
    p.add_argument(
        "-i", "--interval",
        type=float,
        default=2.0,
        metavar="SEC",
        help="seconds between pings (default: 2.0, min: 0.5)",
    )
    p.add_argument(
        "-l", "--log",
        metavar="FILE",
        help="append human-readable log to FILE",
    )
    p.add_argument(
        "-j", "--json-report",
        metavar="FILE",
        help="write machine-readable JSON report to FILE on exit",
    )
    p.add_argument(
        "--no-color",
        action="store_true",
        help="disable ANSI color output",
    )
    p.add_argument(
        "-q", "--quiet",
        action="store_true",
        help="suppress the live status ticker (only print state changes)",
    )
    p.add_argument(
        "-v", "--version",
        action="version",
        version=f"checkup {__version__}",
    )
    return p


def main() -> None:
    parser = _build_parser()
    args   = parser.parse_args()

    if args.interval < 0.5:
        parser.error("--interval must be >= 0.5 seconds")

    if args.no_color:
        global _USE_COLOR
        _USE_COLOR = False

    monitor = CheckupMonitor(
        target      = args.target,
        interval    = args.interval,
        log_file    = args.log,
        json_report = args.json_report,
        quiet       = args.quiet,
    )
    monitor.run()


if __name__ == "__main__":
    main()
