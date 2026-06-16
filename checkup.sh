#!/usr/bin/env bash
#
# checkup — Lightweight Network Uptime Monitor (Bash edition)
# Zero dependencies — uses only standard POSIX/Linux utilities:
#   ping, date, awk, grep, sleep, bc (optional — for sub-second intervals)
#
# https://github.com/your-username/checkup
#
# Usage:
#   checkup.sh <TARGET> [OPTIONS]
#
# Options:
#   -i, --interval SEC     seconds between pings (default: 2, min: 1)
#   -l, --log FILE         append log to FILE
#       --no-color         disable ANSI color output
#   -q, --quiet            suppress live status ticker
#   -v, --version          print version and exit
#   -h, --help             print this help and exit

set -euo pipefail

VERSION="1.0.0"

# ---------------------------------------------------------------------------
# ANSI color codes (disabled when output is not a TTY)
# ---------------------------------------------------------------------------

if [[ -t 1 ]]; then
    RED='\033[91m'; GREEN='\033[92m'; YELLOW='\033[93m'
    CYAN='\033[96m'; WHITE='\033[97m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; WHITE=''; BOLD=''; DIM=''; RESET=''
fi

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

TARGET=""
INTERVAL=2
LOG_FILE=""
NO_COLOR=false
QUIET=false

SESSION_START=""
PREVIOUS_STATE=""
DOWNTIME_START_TS=""
DOWNTIME_START_EPOCH=0

PING_COUNT=0
PING_SUCCESS=0
TOTAL_DOWNTIME=0
INCIDENT_COUNT=0

# Temp file stores incidents as: lost_ts|restored_ts|duration_secs
INCIDENT_FILE="/tmp/checkup_incidents_$$.tmp"

ON_LIVE_LINE=false   # true when cursor is on a \r-overwritable line

# ---------------------------------------------------------------------------
# Cleanup on exit
# ---------------------------------------------------------------------------

cleanup() {
    rm -f "$INCIDENT_FILE"
}
trap cleanup EXIT

# ---------------------------------------------------------------------------
# Signal handler — graceful shutdown
# ---------------------------------------------------------------------------

handle_shutdown() {
    echo  # end live line if active
    ON_LIVE_LINE=false
    log_msg "${DIM}[INFO] Monitoring stopped by user (Ctrl+C)${RESET}"
    print_summary
    exit 0
}
trap handle_shutdown SIGINT SIGTERM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

disable_color() {
    RED=''; GREEN=''; YELLOW=''; CYAN=''; WHITE=''; BOLD=''; DIM=''; RESET=''
}

log_msg() {
    local message="$1"
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')

    # If cursor is on a live line, move to a new line first
    if [[ "$ON_LIVE_LINE" == true ]]; then
        echo
        ON_LIVE_LINE=false
    fi

    local line="[${ts}] ${message}"
    echo -e "$line"

    if [[ -n "$LOG_FILE" ]]; then
        # Strip ANSI codes before writing to file
        echo -e "$line" | sed 's/\x1b\[[0-9;]*m//g' >> "$LOG_FILE" 2>/dev/null \
            || echo "Warning: cannot write to log file" >&2
    fi
}

live_status() {
    [[ "$QUIET" == true ]] && return
    printf "\r  %b   " "$1"
    ON_LIVE_LINE=true
}

separator() {
    local char="${1:--}"
    local width="${2:-60}"
    local line
    line=$(printf '%*s' "$width" '' | tr ' ' "$char")
    log_msg "${DIM}${line}${RESET}"
}

fmt_duration() {
    local total_secs=$1
    local minutes=$(( total_secs / 60 ))
    local secs=$(( total_secs % 60 ))

    if (( total_secs < 60 )); then
        echo "${total_secs} seconds"
    elif (( minutes == 1 )); then
        echo "${minutes} minute, ${secs} seconds"
    else
        echo "${minutes} minutes, ${secs} seconds"
    fi
}

# ---------------------------------------------------------------------------
# Ping
# ---------------------------------------------------------------------------

do_ping() {
    if ping -c 1 -W 2 "$TARGET" >/dev/null 2>&1; then
        echo "UP"
    else
        echo "DOWN"
    fi
}

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

print_header() {
    local w=60
    echo
    echo -e "${BOLD}${CYAN}$(printf '=%.0s' $(seq 1 $w))${RESET}"
    echo -e "${BOLD}${WHITE}  checkup  —  Network Uptime Monitor${RESET}"
    echo -e "${BOLD}${CYAN}$(printf '=%.0s' $(seq 1 $w))${RESET}"
    log_msg "  Session Started : ${WHITE}${SESSION_START}${RESET}"
    log_msg "  Target          : ${WHITE}${TARGET}${RESET}"
    log_msg "  Ping Interval   : ${WHITE}${INTERVAL}s${RESET}"
    [[ -n "$LOG_FILE" ]] && log_msg "  Log File        : ${WHITE}${LOG_FILE}${RESET}"
    echo -e "${BOLD}${CYAN}$(printf -- '-%.0s' $(seq 1 $w))${RESET}"
    echo
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print_summary() {
    local now
    now=$(date '+%Y-%m-%d %H:%M:%S')

    local start_epoch end_epoch session_secs
    start_epoch=$(date -d "$SESSION_START" +%s 2>/dev/null || date -j -f '%Y-%m-%d %H:%M:%S' "$SESSION_START" +%s)
    end_epoch=$(date +%s)
    session_secs=$(( end_epoch - start_epoch ))

    local loss_pct=0
    if (( PING_COUNT > 0 )); then
        local failed=$(( PING_COUNT - PING_SUCCESS ))
        loss_pct=$(awk "BEGIN { printf \"%.1f\", ($failed / $PING_COUNT) * 100 }")
    fi

    echo
    echo -e "${BOLD}${CYAN}$(printf '=%.0s' $(seq 1 60))${RESET}"
    echo -e "${BOLD}${WHITE}  SESSION SUMMARY${RESET}"
    echo -e "${BOLD}${CYAN}$(printf '=%.0s' $(seq 1 60))${RESET}"

    log_msg "  Ended           : ${now}"
    log_msg "  Session Duration: $(fmt_duration "$session_secs")"
    log_msg "  Pings Sent      : ${PING_COUNT}"
    log_msg "  Packet Loss     : ${loss_pct}%"
    echo

    if [[ ! -s "$INCIDENT_FILE" ]]; then
        log_msg "${GREEN}${BOLD}  Status: No downtime detected — target was UP the entire session.${RESET}"
    else
        INCIDENT_COUNT=$(wc -l < "$INCIDENT_FILE")
        log_msg "${YELLOW}  Downtime Events : ${INCIDENT_COUNT}${RESET}"
        log_msg "${YELLOW}  Total Downtime  : $(fmt_duration "$TOTAL_DOWNTIME")${RESET}"
        echo
        echo -e "${BOLD}  Incident Log${RESET}"
        echo -e "${DIM}  $(printf -- '-%.0s' $(seq 1 56))${RESET}"

        local idx=0
        while IFS='|' read -r lost_ts restored_ts dur_secs; do
            (( idx++ ))
            echo
            log_msg "  [${idx}] LOST     : ${RED}${lost_ts}${RESET}"
            log_msg "      RESTORED : ${GREEN}${restored_ts}${RESET}"
            log_msg "      Duration : ${YELLOW}$(fmt_duration "$dur_secs")${RESET}"
        done < "$INCIDENT_FILE"
    fi

    echo
    echo -e "${BOLD}${CYAN}$(printf '=%.0s' $(seq 1 60))${RESET}"
    echo
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

print_usage() {
    cat <<EOF
Usage: checkup.sh <TARGET> [OPTIONS]

Monitor network connectivity to an IP address or hostname.

Arguments:
  TARGET              IP address or hostname to monitor

Options:
  -i, --interval SEC  seconds between pings (default: 2, minimum: 1)
  -l, --log FILE      append human-readable log to FILE
      --no-color      disable ANSI color output
  -q, --quiet         suppress live status ticker
  -v, --version       print version and exit
  -h, --help          print this help and exit

Examples:
  checkup.sh 8.8.8.8
  checkup.sh google.com --interval 1
  checkup.sh 192.168.1.1 --interval 2 --log uptime.log
  checkup.sh 10.0.0.1 --no-color > uptime.txt
EOF
}

parse_args() {
    if (( $# == 0 )); then
        print_usage
        exit 1
    fi

    # First pass: handle --help / --version / -h / -v before consuming TARGET
    for arg in "$@"; do
        case "$arg" in
            -h|--help)    print_usage; exit 0 ;;
            -v|--version) echo "checkup $VERSION"; exit 0 ;;
        esac
    done

    TARGET="$1"
    shift

    while (( $# > 0 )); do
        case "$1" in
            -i|--interval)
                INTERVAL="${2:?'--interval requires a value'}"; shift 2 ;;
            -l|--log)
                LOG_FILE="${2:?'--log requires a value'}"; shift 2 ;;
            --no-color)
                NO_COLOR=true; shift ;;
            -q|--quiet)
                QUIET=true; shift ;;
            *)
                echo "Unknown option: $1" >&2; print_usage; exit 1 ;;
        esac
    done

    if (( INTERVAL < 1 )); then
        echo "Error: --interval must be >= 1 second (Bash version)" >&2
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

main() {
    parse_args "$@"
    [[ "$NO_COLOR" == true ]] && disable_color

    : > "$INCIDENT_FILE"   # truncate/create temp file

    SESSION_START=$(date '+%Y-%m-%d %H:%M:%S')
    print_header

    # Establish initial state
    PREVIOUS_STATE=$(do_ping)
    (( PING_COUNT++ ))
    [[ "$PREVIOUS_STATE" == "UP" ]] && (( PING_SUCCESS++ ))

    if [[ "$PREVIOUS_STATE" == "UP" ]]; then
        log_msg "[INFO]  Initial status: ${GREEN}${BOLD}UP${RESET}"
    else
        log_msg "[INFO]  Initial status: ${RED}${BOLD}DOWN${RESET}"
        DOWNTIME_START_TS=$(date '+%Y-%m-%d %H:%M:%S')
        DOWNTIME_START_EPOCH=$(date +%s)
    fi

    while true; do
        sleep "$INTERVAL"

        local current_state now now_epoch
        current_state=$(do_ping)
        now=$(date '+%Y-%m-%d %H:%M:%S')
        now_epoch=$(date +%s)

        (( PING_COUNT++ ))
        [[ "$current_state" == "UP" ]] && (( PING_SUCCESS++ ))

        # ── UP → DOWN ────────────────────────────────────────────────────
        if [[ "$PREVIOUS_STATE" == "UP" && "$current_state" == "DOWN" ]]; then
            DOWNTIME_START_TS="$now"
            DOWNTIME_START_EPOCH="$now_epoch"
            echo  # end live line
            ON_LIVE_LINE=false
            separator "─"
            log_msg "${RED}${BOLD}[ALERT] Connection LOST at: ${now}${RESET}"
            separator "─"

        # ── DOWN → UP ────────────────────────────────────────────────────
        elif [[ "$PREVIOUS_STATE" == "DOWN" && "$current_state" == "UP" ]]; then
            local dur=$(( now_epoch - DOWNTIME_START_EPOCH ))
            (( TOTAL_DOWNTIME += dur ))
            separator "─"
            log_msg "${GREEN}${BOLD}[INFO]    Connection RESTORED at: ${now}${RESET}"
            log_msg "${YELLOW}[SUMMARY] Total Downtime Duration: $(fmt_duration "$dur")${RESET}"
            separator "─"
            echo
            echo "${DOWNTIME_START_TS}|${now}|${dur}" >> "$INCIDENT_FILE"

        # ── Steady UP: live ticker ────────────────────────────────────────
        elif [[ "$PREVIOUS_STATE" == "UP" && "$current_state" == "UP" ]]; then
            live_status "${GREEN}●${RESET}  ${now}"

        # ── Steady DOWN: elapsed counter ─────────────────────────────────
        elif [[ "$PREVIOUS_STATE" == "DOWN" && "$current_state" == "DOWN" ]]; then
            local elapsed=$(( now_epoch - DOWNTIME_START_EPOCH ))
            live_status "${RED}●${RESET}  ${now}  still DOWN — $(fmt_duration "$elapsed")"
        fi

        PREVIOUS_STATE="$current_state"
    done
}

main "$@"
