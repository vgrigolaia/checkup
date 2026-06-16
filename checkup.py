#!/usr/bin/env python3
"""
checkup — Lightweight Network Uptime Monitor
Zero external dependencies. Python 3.6+ standard library only.
https://github.com/vgrigolaia/checkup

Usage:
  checkup.py 8.8.8.8
  checkup.py 8.8.8.8 1.1.1.1 192.168.1.1        # multi-host
  checkup.py google.com:443 10.0.0.1:22          # TCP port check per host
  checkup.py 10.0.0.1 --interval 1 --log out.log
"""

import argparse
import json
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from datetime import datetime

__version__ = "1.2.0"

# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------

class _C:
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    WHITE  = "\033[97m"
    BOLD   = "\033[1m"
    DIM    = "\033[2m"
    RESET  = "\033[0m"

_COLOR = sys.stdout.isatty()


def c(code: str, text: str) -> str:
    return f"{code}{text}{_C.RESET}" if _COLOR else text


def strip_ansi(s: str) -> str:
    return re.sub(r"\033\[[0-9;]*m", "", s)


def pad(text: str, width: int) -> str:
    """Left-pad plain text to width, ignoring ANSI codes."""
    plain_len = len(strip_ansi(text))
    return text + " " * max(0, width - plain_len)


# ---------------------------------------------------------------------------
# Duration formatting
# ---------------------------------------------------------------------------

def fmt_short(secs: float) -> str:
    s = int(secs)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m"


def fmt_long(secs: float) -> str:
    s = int(secs)
    if s < 60:
        return f"{s} second{'s' if s != 1 else ''}"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m} minute{'s' if m != 1 else ''}, {s} second{'s' if s != 1 else ''}"
    h, m = divmod(m, 60)
    return (f"{h} hour{'s' if h != 1 else ''}, "
            f"{m} minute{'s' if m != 1 else ''}, "
            f"{s} second{'s' if s != 1 else ''}")


# ---------------------------------------------------------------------------
# Network check functions (stdlib only)
# ---------------------------------------------------------------------------

def icmp_check(host: str):
    """ICMP ping via system ping binary. Returns (is_up, rtt_ms)."""
    try:
        proc = subprocess.run(
            ["ping", "-c", "1", "-W", "2", host],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
        if proc.returncode == 0:
            m = re.search(r"time[=<]([\d.]+)\s*ms", proc.stdout.decode())
            return True, float(m.group(1)) if m else None
        return False, None
    except subprocess.TimeoutExpired:
        return False, None
    except FileNotFoundError:
        sys.exit(c(_C.RED, "Error: 'ping' not found on this system."))
    except Exception:
        return False, None


def tcp_check(host: str, port: int):
    """TCP connect check. Returns (is_up, rtt_ms)."""
    start = time.monotonic()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        err = sock.connect_ex((host, port))
        rtt = (time.monotonic() - start) * 1000
        sock.close()
        return err == 0, round(rtt, 1) if err == 0 else None
    except Exception:
        return False, None


# ---------------------------------------------------------------------------
# HostWatcher — monitors one host in a background thread
# ---------------------------------------------------------------------------

class HostWatcher:
    def __init__(self, target: str, port, interval: float, on_event):
        self.target   = target
        self.port     = port        # int or None
        self.interval = interval
        self.on_event = on_event    # callback(watcher, event_type, now, extra)

        self._lock    = threading.Lock()

        # State fields (always access under _lock)
        self.is_up          = None
        self.last_rtt       = None
        self.uptime_start   = None
        self.downtime_start = None
        self.ping_count     = 0
        self.ping_success   = 0
        self.rtt_samples    = []
        self.downtime_events = []

        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    @property
    def check_label(self) -> str:
        return f"TCP:{self.port}" if self.port else "ICMP"

    def _do_check(self):
        if self.port:
            return tcp_check(self.target, self.port)
        return icmp_check(self.target)

    def _run(self):
        while True:
            is_up, rtt = self._do_check()
            now = datetime.now()

            with self._lock:
                self.ping_count += 1
                if is_up:
                    self.ping_success += 1
                    if rtt is not None:
                        self.rtt_samples.append(rtt)
                self.last_rtt = rtt
                prev          = self.is_up
                self.is_up    = is_up

                # First check
                if prev is None:
                    if is_up:
                        self.uptime_start = now
                    else:
                        self.downtime_start = now
                    self.on_event(self, "init", now, rtt)

                # UP → DOWN
                elif prev is True and not is_up:
                    self.downtime_start = now
                    self.uptime_start   = None
                    self.on_event(self, "down", now, None)

                # DOWN → UP
                elif prev is False and is_up:
                    dur = (now - self.downtime_start).total_seconds()
                    self.downtime_events.append({
                        "lost_at":     self.downtime_start,
                        "restored_at": now,
                        "duration":    dur,
                    })
                    self.uptime_start   = now
                    self.downtime_start = None
                    self.on_event(self, "up", now, dur)

            time.sleep(self.interval)

    def snapshot(self) -> dict:
        """Thread-safe read of all display-relevant state."""
        with self._lock:
            return {
                "target":          self.target,
                "check_label":     self.check_label,
                "is_up":           self.is_up,
                "last_rtt":        self.last_rtt,
                "uptime_start":    self.uptime_start,
                "downtime_start":  self.downtime_start,
                "ping_count":      self.ping_count,
                "ping_success":    self.ping_success,
                "rtt_samples":     list(self.rtt_samples),
                "downtime_events": list(self.downtime_events),
            }


# ---------------------------------------------------------------------------
# Live table display
# ---------------------------------------------------------------------------

class TableDisplay:
    MAX_EVENTS = 8   # recent events shown below the table

    def __init__(self, watchers, log_file=None):
        self.watchers    = watchers
        self.log_file    = log_file
        self._events     = deque(maxlen=self.MAX_EVENTS)
        self._lock       = threading.Lock()
        self._drawn_rows = 0    # how many rows have been drawn (for cursor-up)
        self._first_draw = True

        # Column widths (auto-sized to longest target name)
        target_max = max(len(w.target) for w in watchers)
        self._col_target = max(target_max, 15)
        self._col_check  = 9    # "TCP:65535"
        self._col_status = 10   # "✗ DOWN"
        self._col_rtt    = 10   # "1234.5ms"
        self._col_dur    = 14   # "up 10h 59m 59s"

    def add_event(self, line: str):
        with self._lock:
            ts  = datetime.now().strftime("%H:%M:%S")
            plain = strip_ansi(line)
            entry = f"  {c(_C.DIM, ts)}  {line}"
            self._events.append(entry)
            if self.log_file:
                try:
                    with open(self.log_file, "a") as f:
                        f.write(f"[{ts}] {plain}\n")
                except IOError:
                    pass

    def _header_lines(self) -> list:
        w = self._col_target + self._col_check + self._col_status + self._col_rtt + self._col_dur + 10
        sep = "─" * w
        lines = [
            c(_C.BOLD + _C.CYAN, "=" * w),
            c(_C.BOLD + _C.WHITE, "  checkup  —  Network Uptime Monitor") +
            c(_C.DIM, f"   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"),
            c(_C.BOLD + _C.CYAN, "=" * w),
            "  " + c(_C.BOLD, pad("TARGET",  self._col_target)) +
            "  " + c(_C.BOLD, pad("CHECK",   self._col_check)) +
            "  " + c(_C.BOLD, pad("STATUS",  self._col_status)) +
            "  " + c(_C.BOLD, pad("RTT",     self._col_rtt)) +
            "  " + c(_C.BOLD, "UPTIME / DOWNTIME"),
            c(_C.DIM, "  " + sep),
        ]
        return lines

    def _format_row(self, snap: dict) -> str:
        now = datetime.now()

        # Status + color
        if snap["is_up"] is None:
            status_str = c(_C.DIM,    pad("...",   self._col_status))
        elif snap["is_up"]:
            status_str = c(_C.GREEN,  pad("● UP",  self._col_status))
        else:
            status_str = c(_C.RED,    pad("✗ DOWN", self._col_status))

        # RTT
        rtt = snap["last_rtt"]
        if rtt is not None and snap["is_up"]:
            rtt_str = c(_C.WHITE, pad(f"{rtt:.1f}ms", self._col_rtt))
        else:
            rtt_str = c(_C.DIM,   pad("--",           self._col_rtt))

        # Duration (uptime streak or downtime elapsed)
        dur_str = c(_C.DIM, pad("--", self._col_dur))
        if snap["is_up"] and snap["uptime_start"]:
            elapsed = (now - snap["uptime_start"]).total_seconds()
            dur_str = c(_C.GREEN, pad("up " + fmt_short(elapsed), self._col_dur))
        elif snap["is_up"] is False and snap["downtime_start"]:
            elapsed = (now - snap["downtime_start"]).total_seconds()
            dur_str = c(_C.RED, pad("down " + fmt_short(elapsed), self._col_dur))

        return (
            "  " + c(_C.WHITE, pad(snap["target"],      self._col_target)) +
            "  " + c(_C.DIM,   pad(snap["check_label"], self._col_check)) +
            "  " + status_str +
            "  " + rtt_str +
            "  " + dur_str
        )

    def _event_section(self) -> list:
        with self._lock:
            events = list(self._events)
        if not events:
            return []
        w = self._col_target + self._col_check + self._col_status + self._col_rtt + self._col_dur + 10
        lines = [
            "",
            c(_C.DIM, "  " + "─" * w),
            "  " + c(_C.BOLD, "Recent Events"),
            c(_C.DIM, "  " + "─" * w),
        ]
        lines += events
        return lines

    def redraw(self):
        snaps  = [w.snapshot() for w in self.watchers]
        header = self._header_lines()         # 5 lines
        rows   = [self._format_row(s) for s in snaps]
        w = self._col_target + self._col_check + self._col_status + self._col_rtt + self._col_dur + 10
        footer = [c(_C.DIM, "  " + "─" * w)]
        events = self._event_section()

        all_lines = header + rows + footer + events

        out = []
        if not self._first_draw:
            # Move cursor up past everything we drew last time
            out.append(f"\033[{self._drawn_rows}A")

        for line in all_lines:
            out.append(f"\r\033[2K{line}")

        sys.stdout.write("\n".join(out) + "\n")
        sys.stdout.flush()

        self._drawn_rows = len(all_lines)
        self._first_draw = False


# ---------------------------------------------------------------------------
# Single-host display (original ticker style, kept for 1-target runs)
# ---------------------------------------------------------------------------

class SingleDisplay:
    def __init__(self, watcher, log_file=None):
        self.watcher   = watcher
        self.log_file  = log_file
        self._on_live  = False

    def _write_log(self, line: str):
        if self.log_file:
            try:
                with open(self.log_file, "a") as f:
                    f.write(strip_ansi(line) + "\n")
            except IOError:
                pass

    def _end_live(self):
        if self._on_live:
            print()
            self._on_live = False

    def log(self, msg: str):
        self._end_live()
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        self._write_log(line)

    def sub(self, msg: str):
        self._end_live()
        line = f"            {msg}"
        print(line)
        self._write_log(line)

    def sep(self, char="─", width=58):
        self._end_live()
        line = f"  {c(_C.DIM, char * width)}"
        print(line)
        self._write_log(line)

    def live(self, msg: str):
        print(f"\r  {msg}   ", end="", flush=True)
        self._on_live = True

    def header(self):
        snap = self.watcher.snapshot()
        w    = 60
        ts   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print()
        print(c(_C.BOLD + _C.CYAN,  "=" * w))
        print(c(_C.BOLD + _C.WHITE, "  checkup  —  Network Uptime Monitor"))
        print(c(_C.BOLD + _C.CYAN,  "=" * w))
        self.log(f"  Target          : {c(_C.WHITE, snap['target'])}")
        self.log(f"  Check           : {c(_C.WHITE, snap['check_label'])}")
        self.log(f"  Session Started : {c(_C.WHITE, ts)}")
        self.log(f"  Ping Interval   : {c(_C.WHITE, str(self.watcher.interval) + 's')}")
        if self.log_file:
            self.log(f"  Log File        : {c(_C.WHITE, self.log_file)}")
        print(c(_C.BOLD + _C.CYAN,  "-" * w))
        print()

    def on_event(self, watcher, event_type: str, now: datetime, extra):
        ts  = now.strftime("%Y-%m-%d %H:%M:%S")
        if event_type == "init":
            rtt_str = f"  (RTT: {extra:.1f} ms)" if extra else ""
            if watcher.is_up:
                self.log(f"{c(_C.GREEN+_C.BOLD, '[  UP  ]')}  Host is {c(_C.GREEN,'ALIVE')}{rtt_str}")
            else:
                self.sep()
                self.log(f"{c(_C.RED+_C.BOLD, '[ DOWN ]')}  Host is {c(_C.RED,'UNREACHABLE')}")
                self.sub(f"  Down since : {c(_C.RED, ts)}")
                self.sep()

        elif event_type == "down":
            self._end_live()
            print()
            self.sep()
            self.log(f"{c(_C.RED+_C.BOLD, '[ DOWN ]')}  Host went {c(_C.RED,'UNREACHABLE')}")
            self.sub(f"  Down since : {c(_C.RED, ts)}")
            self.sep()

        elif event_type == "up":
            duration = extra
            snap     = watcher.snapshot()
            lost_ts  = snap["downtime_events"][-1]["lost_at"].strftime("%Y-%m-%d %H:%M:%S") \
                       if snap["downtime_events"] else "unknown"
            print()
            self.sep()
            self.log(f"{c(_C.GREEN+_C.BOLD, '[  UP  ]')}  Host is {c(_C.GREEN,'BACK ONLINE')}")
            self.sub(f"  Came back  : {c(_C.GREEN, ts)}")
            self.sub(f"  Was down   : {c(_C.RED, lost_ts)}  →  {c(_C.GREEN, ts)}")
            self.sub(f"  Total down : {c(_C.YELLOW, fmt_long(duration))}")
            self.sep()
            print()

    def tick(self):
        snap = self.watcher.snapshot()
        now  = datetime.now()
        if snap["is_up"] is None:
            return
        if snap["is_up"]:
            rtt_str = f"  (RTT: {snap['last_rtt']:.1f} ms)" if snap["last_rtt"] else ""
            up_for  = ""
            if snap["uptime_start"]:
                up_for = c(_C.DIM, "  up " + fmt_short((now - snap["uptime_start"]).total_seconds()))
            self.live(c(_C.GREEN,"●") + f"  {now.strftime('%H:%M:%S')}  "
                      f"Host is {c(_C.GREEN,'ALIVE')}{rtt_str}{up_for}")
        else:
            if snap["downtime_start"]:
                elapsed = (now - snap["downtime_start"]).total_seconds()
                self.live(c(_C.RED,"✗") + f"  {now.strftime('%H:%M:%S')}  "
                          f"Still {c(_C.RED,'DOWN')} — {fmt_short(elapsed)}")

    def summary(self, session_start: datetime):
        snap    = self.watcher.snapshot()
        now     = datetime.now()
        secs    = (now - session_start).total_seconds()
        loss    = ((snap["ping_count"] - snap["ping_success"]) / snap["ping_count"] * 100
                   if snap["ping_count"] else 0.0)
        samples = snap["rtt_samples"]

        self._end_live()
        print()
        print(c(_C.BOLD + _C.CYAN,  "=" * 60))
        print(c(_C.BOLD + _C.WHITE, "  SESSION SUMMARY"))
        print(c(_C.BOLD + _C.CYAN,  "=" * 60))
        self.log(f"  Ended            : {now.strftime('%Y-%m-%d %H:%M:%S')}")
        self.log(f"  Session Duration : {fmt_long(secs)}")
        self.log(f"  Pings Sent       : {snap['ping_count']}")
        self.log(f"  Packet Loss      : {loss:.1f}%")
        if samples:
            self.log(f"  RTT min/avg/max  : "
                     f"{min(samples):.1f} / {sum(samples)/len(samples):.1f} / {max(samples):.1f} ms")
        print()
        events = snap["downtime_events"]
        if not events:
            self.log(c(_C.GREEN + _C.BOLD,
                       "  Status: No downtime detected — host was UP the entire session."))
        else:
            total_down = sum(e["duration"] for e in events)
            self.log(c(_C.YELLOW, f"  Downtime Events  : {len(events)}"))
            self.log(c(_C.YELLOW, f"  Total Time DOWN  : {fmt_long(total_down)}"))
            print()
            print(c(_C.BOLD, "  Incident Log"))
            print(c(_C.DIM,  "  " + "-" * 56))
            for i, ev in enumerate(events, 1):
                print()
                self.sub(c(_C.BOLD, f"Incident #{i}"))
                self.sub(f"  Went DOWN  : {c(_C.RED,    ev['lost_at'].strftime('%Y-%m-%d %H:%M:%S'))}")
                self.sub(f"  Came UP    : {c(_C.GREEN,  ev['restored_at'].strftime('%Y-%m-%d %H:%M:%S'))}")
                self.sub(f"  Down for   : {c(_C.YELLOW, fmt_long(ev['duration']))}")
        print()
        print(c(_C.BOLD + _C.CYAN, "=" * 60))
        print()


# ---------------------------------------------------------------------------
# Multi-host summary on exit
# ---------------------------------------------------------------------------

def multi_summary(watchers, session_start: datetime, log_file=None):
    now  = datetime.now()
    secs = (now - session_start).total_seconds()
    w    = 60

    def pr(msg):
        ts   = now.strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        if log_file:
            try:
                with open(log_file, "a") as f:
                    f.write(strip_ansi(line) + "\n")
            except IOError:
                pass

    print()
    print(c(_C.BOLD + _C.CYAN,  "=" * w))
    print(c(_C.BOLD + _C.WHITE, "  SESSION SUMMARY"))
    print(c(_C.BOLD + _C.CYAN,  "=" * w))
    pr(f"  Ended            : {now.strftime('%Y-%m-%d %H:%M:%S')}")
    pr(f"  Session Duration : {fmt_long(secs)}")
    print()

    for watcher in watchers:
        snap    = watcher.snapshot()
        loss    = ((snap["ping_count"] - snap["ping_success"]) / snap["ping_count"] * 100
                   if snap["ping_count"] else 0.0)
        samples = snap["rtt_samples"]
        events  = snap["downtime_events"]
        total_d = sum(e["duration"] for e in events)

        print(c(_C.BOLD, f"  [{snap['target']}]  ({snap['check_label']})"))
        pr(f"    Pings Sent      : {snap['ping_count']}")
        pr(f"    Packet Loss     : {loss:.1f}%")
        if samples:
            pr(f"    RTT min/avg/max : "
               f"{min(samples):.1f} / {sum(samples)/len(samples):.1f} / {max(samples):.1f} ms")
        if not events:
            pr(c(_C.GREEN, "    Status: No downtime detected."))
        else:
            pr(c(_C.YELLOW, f"    Downtime Events  : {len(events)}"))
            pr(c(_C.YELLOW, f"    Total Time DOWN  : {fmt_long(total_d)}"))
            for i, ev in enumerate(events, 1):
                pr(f"      [{i}] {ev['lost_at'].strftime('%H:%M:%S')} → "
                   f"{ev['restored_at'].strftime('%H:%M:%S')}  "
                   f"({fmt_long(ev['duration'])})")
        print()

    print(c(_C.BOLD + _C.CYAN, "=" * w))
    print()


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def parse_target(raw: str):
    """Parse 'host' or 'host:port'. Returns (host, port_or_None)."""
    if ":" in raw:
        host, port_str = raw.rsplit(":", 1)
        try:
            return host, int(port_str)
        except ValueError:
            sys.exit(f"Error: invalid port in '{raw}'")
    return raw, None


def run(args):
    session_start = datetime.now()
    targets       = [parse_target(t) for t in args.targets]
    multi         = len(targets) > 1

    # Build watchers (event callbacks wired up after displays are created)
    watchers = []
    for host, port in targets:
        port = port or args.port
        watchers.append(HostWatcher(host, port, args.interval, on_event=None))

    if multi:
        display = TableDisplay(watchers, log_file=args.log)

        def on_event(watcher, event_type, now, extra):
            ts  = now.strftime("%H:%M:%S")
            tgt = c(_C.WHITE, f"[{watcher.target}]")
            if event_type == "down":
                display.add_event(f"{tgt}  {c(_C.RED+_C.BOLD, 'DOWN')} — host went unreachable at {ts}")
            elif event_type == "up":
                display.add_event(f"{tgt}  {c(_C.GREEN+_C.BOLD, 'UP')} — restored after {c(_C.YELLOW, fmt_long(extra))}")
            elif event_type == "init":
                status = c(_C.GREEN, "UP") if watcher.is_up else c(_C.RED, "DOWN")
                display.add_event(f"{tgt}  initial status: {status}")

    else:
        disp = SingleDisplay(watchers[0], log_file=args.log)
        disp.header()

        def on_event(watcher, event_type, now, extra):
            disp.on_event(watcher, event_type, now, extra)

    for w in watchers:
        w.on_event = on_event

    def shutdown(_sig, _frame):
        print()
        if multi:
            print()
            print(c(_C.DIM, "[INFO] Monitoring stopped by user (Ctrl+C)"))
            multi_summary(watchers, session_start, args.log)
        else:
            disp._end_live()
            print()
            print(c(_C.DIM, "[INFO] Monitoring stopped by user (Ctrl+C)"))
            disp.summary(session_start)
        sys.exit(0)

    signal.signal(signal.SIGINT,  shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # Start all watcher threads
    for w in watchers:
        w.start()

    # Display loop
    if multi:
        # Wait for first results before drawing
        time.sleep(args.interval + 0.5)
        while True:
            display.redraw()
            time.sleep(args.interval)
    else:
        while True:
            disp.tick()
            time.sleep(args.interval)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser():
    p = argparse.ArgumentParser(
        prog="checkup",
        description="Lightweight network uptime monitor. Zero external dependencies.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  checkup.py 8.8.8.8
  checkup.py 8.8.8.8 1.1.1.1 192.168.1.1          # monitor multiple hosts
  checkup.py google.com:443 10.0.0.1:22            # TCP port check per host
  checkup.py 10.0.0.1 --port 80                    # TCP check, single host
  checkup.py 8.8.8.8 --interval 1 --log uptime.log
        """,
    )
    p.add_argument(
        "targets",
        nargs="+",
        metavar="TARGET",
        help="host(s) to monitor — use host:port for TCP checks (e.g. google.com:443)",
    )
    p.add_argument("-i", "--interval", type=float, default=2.0, metavar="SEC",
                   help="seconds between checks (default: 2.0, min: 0.5)")
    p.add_argument("-l", "--log", metavar="FILE",
                   help="append plain-text log to FILE")
    p.add_argument("-p", "--port", type=int, default=None, metavar="PORT",
                   help="TCP port to check on all hosts (overridden by per-host :port)")
    p.add_argument("--no-color", action="store_true",
                   help="disable ANSI color output")
    p.add_argument("-v", "--version", action="version", version=f"checkup {__version__}")
    return p


def main():
    p    = build_parser()
    args = p.parse_args()

    if args.interval < 0.5:
        p.error("--interval must be >= 0.5 seconds")

    if args.no_color:
        global _COLOR
        _COLOR = False

    run(args)


if __name__ == "__main__":
    main()
