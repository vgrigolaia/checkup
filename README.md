# checkup — Network Uptime Monitor

> Lightweight, zero-dependency network uptime monitor for Linux.  
> Detects outages, measures downtime, and produces clean human-readable reports — with no `pip install` required.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.6+](https://img.shields.io/badge/python-3.6%2B-blue.svg)](https://www.python.org/)
[![Shell: Bash 4+](https://img.shields.io/badge/shell-bash%204%2B-green.svg)](https://www.gnu.org/software/bash/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

---

## Features

- **Zero dependencies** — Python standard library only; no `pip install` ever needed
- **Dual implementation** — Python (`checkup.py`) and Bash (`checkup.sh`) versions
- **Live status ticker** — real-time `●  HH:MM:SS  RTT 12.3 ms` line while the host is up
- **Instant outage detection** — timestamps connection loss to the second
- **Downtime duration** — calculates and prints elapsed downtime for every incident
- **Session summary** — packet loss %, RTT min/avg/max, and a full incident log on exit
- **Log file support** — append all events to a plain-text file (ANSI stripped automatically)
- **JSON report** — machine-readable export for dashboards / alerting pipelines (Python only)
- **Color output** — ANSI colors auto-disabled when piped or redirected
- **Graceful shutdown** — `Ctrl+C` always prints a complete summary before exiting

---

## Quick Start

```bash
# Clone
git clone https://github.com/your-username/checkup.git
cd checkup

# Make executable
chmod +x checkup.py checkup.sh

# Run (Python — recommended)
./checkup.py 8.8.8.8

# Run (Bash — no Python needed)
./checkup.sh 8.8.8.8
```

---

## Usage

### Python version

```
./checkup.py <TARGET> [OPTIONS]

Arguments:
  TARGET                IP address or hostname to monitor

Options:
  -i, --interval SEC    seconds between pings  (default: 2.0, min: 0.5)
  -l, --log FILE        append plain-text log to FILE
  -j, --json-report F   write JSON report to FILE on session exit
      --no-color        disable ANSI color output
  -q, --quiet           suppress live status ticker (only print state changes)
  -v, --version         print version and exit
  -h, --help            print help and exit
```

### Bash version

```
./checkup.sh <TARGET> [OPTIONS]

Options:
  -i, --interval SEC    seconds between pings  (default: 2, min: 1)
  -l, --log FILE        append plain-text log to FILE
      --no-color        disable ANSI color output
  -q, --quiet           suppress live status ticker
  -v, --version         print version and exit
  -h, --help            print help and exit
```

---

## Examples

```bash
# Monitor Google DNS, default 2-second interval
./checkup.py 8.8.8.8

# Monitor a hostname with 1-second interval
./checkup.py google.com --interval 1

# Monitor a local gateway, save log to file
./checkup.py 192.168.1.1 --interval 2 --log gateway.log

# Full logging: human-readable log + machine-readable JSON report
./checkup.py 10.0.0.1 --interval 1 --log uptime.log --json-report report.json

# Redirect to file (color auto-disabled)
./checkup.py 8.8.8.8 --no-color > session.txt

# Run in the background, log to file
nohup ./checkup.py 8.8.8.8 --log uptime.log --quiet &

# Bash version on a minimal system without Python
./checkup.sh 192.168.1.1 --interval 2 --log gateway.log
```

---

## Sample Output

```
============================================================
  checkup  —  Network Uptime Monitor
============================================================
[2026-06-16 14:23:45] Session Started : 2026-06-16 14:23:45
[2026-06-16 14:23:45] Target          : 8.8.8.8
[2026-06-16 14:23:45] Ping Interval   : 2.0s
------------------------------------------------------------

[2026-06-16 14:23:45] [INFO]  Initial status: UP  RTT 12.4 ms

  ●  14:23:47  RTT 11.9 ms   ← live ticker (updates in place)

────────────────────────────────────────────────────────────
[2026-06-16 14:26:12] [ALERT] Connection LOST at: 2026-06-16 14:26:12
────────────────────────────────────────────────────────────

  ●  14:26:14  still DOWN — 2s   ← live elapsed counter

────────────────────────────────────────────────────────────
[2026-06-16 14:26:20] [INFO]    Connection RESTORED at: 2026-06-16 14:26:20
[2026-06-16 14:26:20] [SUMMARY] Total Downtime Duration: 8 seconds
────────────────────────────────────────────────────────────

^C
[2026-06-16 14:30:15] [INFO] Monitoring stopped by user (Ctrl+C)

============================================================
  SESSION SUMMARY
============================================================
[2026-06-16 14:30:15] Ended           : 2026-06-16 14:30:15
[2026-06-16 14:30:15] Session Duration: 6 minutes, 30 seconds
[2026-06-16 14:30:15] Pings Sent      : 195
[2026-06-16 14:30:15] Packet Loss     : 0.5%
[2026-06-16 14:30:15] RTT min/avg/max : 10.2 / 13.5 / 22.1 ms

[2026-06-16 14:30:15]   Downtime Events : 1
[2026-06-16 14:30:15]   Total Downtime  : 8 seconds

  Incident Log
  ────────────────────────────────────────────────────────

  [1] LOST     : 2026-06-16 14:26:12
      RESTORED : 2026-06-16 14:26:20
      Duration : 8 seconds

============================================================
```

---

## JSON Report (`--json-report`)

When `--json-report report.json` is passed, checkup writes a structured report on exit:

```json
{
  "session_start": "2026-06-16 14:23:45",
  "session_end":   "2026-06-16 14:30:15",
  "target":        "8.8.8.8",
  "interval_seconds": 2.0,
  "session_duration_seconds": 390,
  "pings_sent":    195,
  "pings_success": 194,
  "packet_loss_pct": 0.51,
  "rtt_ms": { "min": 10.2, "avg": 13.5, "max": 22.1 },
  "downtime_events": 1,
  "total_downtime_seconds": 8,
  "incidents": [
    {
      "lost_at":          "2026-06-16 14:26:12",
      "restored_at":      "2026-06-16 14:26:20",
      "duration_seconds": 8
    }
  ]
}
```

---

## Running as a Background Service

### Simple background process

```bash
nohup ./checkup.py 8.8.8.8 --interval 2 --log /var/log/checkup.log --quiet &
echo "PID: $!"
```

### systemd service (optional)

Create `/etc/systemd/system/checkup.service`:

```ini
[Unit]
Description=checkup Network Uptime Monitor
After=network.target

[Service]
ExecStart=/opt/checkup/checkup.py 8.8.8.8 --interval 2 --log /var/log/checkup.log --quiet
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

| Version | Requirement |
|---|---|
| **Python** | Python 3.6+ — standard library only, zero external packages |
| **Bash**   | Bash 4+, `ping`, `date`, `awk`, `grep`, `sed` (all standard on Linux) |
| **System** | Linux (or any Unix-like OS with `ping` available) |

---

## Project Structure

```
checkup/
├── checkup.py       # Python implementation (recommended)
├── checkup.sh       # Bash implementation (minimal-system fallback)
├── README.md        # This file
├── CONTRIBUTING.md  # How to contribute
├── LICENSE          # MIT License
└── .gitignore
```

---

## Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines on how to open issues, propose features, and submit pull requests.

---

## License

This project is licensed under the **MIT License** — see [LICENSE](LICENSE) for details.

---

## Acknowledgements

Built for sysadmins and DevOps engineers who need a fast, trustworthy outage tracker with no setup friction.  
If `checkup` saved you during an incident, a ⭐ on GitHub is appreciated!
