# checkup — Network Uptime Monitor

> Lightweight, zero-dependency network uptime monitor for Linux.  
> Detects outages, measures downtime, tracks multiple hosts, and produces clean human-readable reports — with no `pip install` required.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.6+](https://img.shields.io/badge/python-3.6%2B-blue.svg)](https://www.python.org/)
[![Shell: Bash 4+](https://img.shields.io/badge/shell-bash%204%2B-green.svg)](https://www.gnu.org/software/bash/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![Version](https://img.shields.io/badge/version-1.2.0-blue.svg)](https://github.com/vgrigolaia/checkup/releases)

---

## Features

- **Zero dependencies** — Python standard library only; no `pip install` ever needed
- **Multi-host monitoring** — watch multiple IPs/hostnames in a single live table
- **TCP port check** — connect to a specific port instead of ICMP ping (useful for hosts that block ping)
- **Dual implementation** — Python (`checkup.py`) and Bash (`checkup.sh`) versions
- **Live status table** — auto-refreshing table with RTT, status, and uptime/downtime per host
- **Uptime streak counter** — shows how long the host has been continuously online
- **Instant outage detection** — timestamps connection loss to the second
- **Downtime duration** — calculates and prints elapsed downtime for every incident
- **Session summary** — packet loss %, RTT min/avg/max, and a full incident log on exit
- **Log file support** — append all events to a plain-text file (ANSI stripped automatically)
- **Color output** — ANSI colors auto-disabled when piped or redirected
- **Graceful shutdown** — `Ctrl+C` always prints a complete per-host summary before exiting

---

## Quick Start

```bash
# Clone
git clone https://github.com/vgrigolaia/checkup.git
cd checkup

# Make executable
chmod +x checkup.py checkup.sh

# Monitor a single host
./checkup.py 8.8.8.8

# Monitor multiple hosts
./checkup.py 8.8.8.8 1.1.1.1 192.168.1.1

# TCP port check
./checkup.py google.com:443 10.0.0.1:22
```

---

## Usage

### Python version (recommended)

```
./checkup.py <TARGET [TARGET ...]> [OPTIONS]

Arguments:
  TARGET     IP or hostname to monitor. Use host:port for TCP check.
             Multiple targets enable multi-host table mode.

Options:
  -i, --interval SEC    seconds between checks  (default: 2.0, min: 0.5)
  -p, --port PORT       TCP port to check on all hosts
  -l, --log FILE        append plain-text log to FILE
      --no-color        disable ANSI color output
  -v, --version         print version and exit
  -h, --help            print help and exit
```

### Bash version

```
./checkup.sh <TARGET> [OPTIONS]

Options:
  -i, --interval SEC    seconds between checks  (default: 2, min: 1)
  -p, --port PORT       TCP port to check instead of ICMP ping
  -l, --log FILE        append plain-text log to FILE
      --no-color        disable ANSI color output
  -v, --version         print version and exit
  -h, --help            print help and exit
```

> **Note:** Multi-host table mode is available in the Python version only.  
> The Bash version supports single-host monitoring with TCP port check.

---

## Examples

```bash
# Single host — ICMP ping, default 2-second interval
./checkup.py 8.8.8.8

# Single host — TCP connect check on port 443
./checkup.py google.com:443

# Single host — TCP check, global port flag
./checkup.py 10.0.0.1 --port 22

# Multi-host — ICMP for all
./checkup.py 8.8.8.8 1.1.1.1 192.168.1.1

# Multi-host — mixed ICMP and TCP per host
./checkup.py 8.8.8.8 google.com:443 10.0.0.1:22 192.168.1.1

# Save log to file
./checkup.py 192.168.1.1 --interval 2 --log gateway.log

# 1-second interval, log everything
./checkup.py 8.8.8.8 1.1.1.1 --interval 1 --log uptime.log

# Run in the background (headless)
nohup ./checkup.py 8.8.8.8 --log /var/log/checkup.log &

# Bash version — TCP check
./checkup.sh 192.168.1.1 --port 80 --interval 2 --log uptime.log
```

---

## Output

### Single host
```
============================================================
  checkup  —  Network Uptime Monitor
============================================================
[2026-06-16 14:23:45]   Target          : 8.8.8.8
[2026-06-16 14:23:45]   Check           : ICMP
[2026-06-16 14:23:45]   Session Started : 2026-06-16 14:23:45
[2026-06-16 14:23:45]   Ping Interval   : 2.0s
------------------------------------------------------------

[2026-06-16 14:23:45] [  UP  ]  Host is ALIVE  (RTT: 12.4 ms)
  ●  14:23:47  Host is ALIVE  (RTT: 11.9 ms)  up 2s

  ────────────────────────────────────────────────────────
[2026-06-16 14:26:12] [ DOWN ]  Host went UNREACHABLE
            Down since : 2026-06-16 14:26:12
  ────────────────────────────────────────────────────────

  ✗  14:26:14  Still DOWN — 2s

  ────────────────────────────────────────────────────────
[2026-06-16 14:26:20] [  UP  ]  Host is BACK ONLINE
            Came back  : 2026-06-16 14:26:20
            Was down   : 2026-06-16 14:26:12  →  2026-06-16 14:26:20
            Total down : 8 seconds
  ────────────────────────────────────────────────────────
```

### Multi-host (live table, redraws every tick)
```
====================================================================
  checkup  —  Network Uptime Monitor        2026-06-16 14:25:34
====================================================================
  TARGET           CHECK    STATUS    RTT         UPTIME / DOWNTIME
  ──────────────────────────────────────────────────────────────────
  8.8.8.8          ICMP     ● UP      35.6ms      up 4m 12s
  1.1.1.1          ICMP     ● UP      38.8ms      up 4m 12s
  google.com       TCP:443  ● UP      39.1ms      up 4m 12s
  192.168.1.1      ICMP     ✗ DOWN    --          down 1m 05s
  ──────────────────────────────────────────────────────────────────

  ──────────────────────────────────────────────────────────────────
  Recent Events
  ──────────────────────────────────────────────────────────────────
  14:23:45  [8.8.8.8]       initial status: UP
  14:23:45  [1.1.1.1]       initial status: UP
  14:23:45  [google.com]    initial status: UP
  14:23:45  [192.168.1.1]   initial status: UP
  14:24:29  [192.168.1.1]   DOWN — host went unreachable at 14:24:29
```

### Session summary on Ctrl+C
```
============================================================
  SESSION SUMMARY
============================================================

  [8.8.8.8]  (ICMP)
    Pings Sent      : 128
    Packet Loss     : 0.0%
    RTT min/avg/max : 10.2 / 13.5 / 22.1 ms
    Status: No downtime detected.

  [192.168.1.1]  (ICMP)
    Pings Sent      : 128
    Packet Loss     : 5.5%
    RTT min/avg/max : 0.8 / 1.2 / 4.3 ms
    Downtime Events  : 2
    Total Time DOWN  : 1 minute, 13 seconds
      [1] 14:24:29 → 14:25:34  (1 minute, 5 seconds)
      [2] 14:26:11 → 14:26:19  (8 seconds)
```

---

## Check Types

| Syntax | Method | When to use |
|---|---|---|
| `checkup.py 8.8.8.8` | ICMP ping | Default — works for most hosts |
| `checkup.py 8.8.8.8 --port 80` | TCP connect | Host blocks ICMP; check HTTP port |
| `checkup.py google.com:443` | TCP connect | Per-host port in multi-host mode |
| `checkup.sh host --port 22` | TCP connect | SSH availability check |

---

## Running as a Background Service

### Simple background process

```bash
nohup ./checkup.py 8.8.8.8 --interval 2 --log /var/log/checkup.log &
echo "PID: $!"
```

### systemd service (optional)

Create `/etc/systemd/system/checkup.service`:

```ini
[Unit]
Description=checkup Network Uptime Monitor
After=network.target

[Service]
ExecStart=/opt/checkup/checkup.py 8.8.8.8 1.1.1.1 --interval 2 --log /var/log/checkup.log
Restart=on-failure
RestartSec=5
StandardOutput=null

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now checkup
sudo journalctl -u checkup -f
```

---

## Requirements

| | Requirement |
|---|---|
| **Python** | Python 3.6+ — standard library only (`socket`, `subprocess`, `threading`) |
| **Bash** | Bash 4+, `ping`, `date`, `awk` (all standard on Linux) |
| **System** | Linux (or any Unix-like OS with `ping` available) |

---

## Project Structure

```
checkup/
├── checkup.py       # Python implementation (recommended)
├── checkup.sh       # Bash implementation (single-host + TCP check)
├── README.md        # This file
├── CONTRIBUTING.md  # How to contribute
├── LICENSE          # MIT License
└── .gitignore
```

---

## Changelog

### v1.2.0
- **Multi-host monitoring** — pass multiple targets, get a live auto-refreshing table
- **TCP port check** — use `host:port` syntax or `--port PORT` flag to check TCP connectivity instead of ICMP
- **Per-host session summary** — Ctrl+C shows RTT stats and incident log for every host
- Bash version gains `--port` flag using `/dev/tcp` built-in (no extra deps)

### v1.1.0
- Clearer `[  UP  ]` / `[ DOWN ]` labels on every state change
- Uptime streak counter in live ticker (`up 3m 42s`)
- Live elapsed downtime counter while host is unreachable
- Fixed Bash `set -e` crash caused by arithmetic on zero values

### v1.0.0
- Initial release: single-host ICMP monitoring, downtime detection, session summary, log file, ANSI colors

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.  
Copyright © 2026 [vgrigolaia](https://github.com/vgrigolaia)
