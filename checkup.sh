#!/usr/bin/env bash
#
# checkup — Network Uptime Monitor (Bash edition)
# Zero dependencies — standard Linux utilities only: ping, date, awk, sleep
#
# https://github.com/vgrigolaia/checkup
#
# Usage:  checkup.sh <TARGET> [OPTIONS]
# Options:
#   -i, --interval SEC    seconds between checks (default: 2, min: 1)
#   -p, --port PORT       TCP port to check instead of ICMP ping
#   -l, --log FILE        append log to FILE
#       --alert-rtt MS    alert when RTT exceeds this threshold (ms)
#       --no-color        disable ANSI colors
#   -v, --version         print version and exit
#   -h, --help            print this help and exit

set -uo pipefail

VERSION="1.3.0"

# ---------------------------------------------------------------------------
# ANSI colors — disabled when stdout is not a TTY
# ---------------------------------------------------------------------------
if [[ -t 1 ]]; then
    RED='\033[91m'; GREEN='\033[92m'; YELLOW='\033[93m'
    CYAN='\033[96m'; WHITE='\033[97m'; BOLD='\033[1m'
    DIM='\033[2m'; RESET='\033[0m'
else
    RED=''; GREEN=''; YELLOW=''; CYAN=''; WHITE=''; BOLD=''; DIM=''; RESET=''
fi

# ---------------------------------------------------------------------------
# Globals
# ---------------------------------------------------------------------------
TARGET=""
PORT=""
INTERVAL=2
LOG_FILE=""
ALERT_RTT=""       # integer ms threshold or empty

SESSION_START=""
SESSION_START_EPOCH=0

STATE=""
DOWNTIME_START_TS=""
DOWNTIME_START_EPOCH=0

PING_COUNT=0
PING_SUCCESS=0
TOTAL_DOWNTIME=0
INCIDENT_COUNT=0
UPTIME_START_EPOCH=0

LAST_RTT=""        # RTT of last successful check (integer ms)
RTT_OVER_LIMIT=false
RTT_ALERT_COUNT=0

INCIDENT_FILE="/tmp/checkup_incidents_$$.tmp"
ON_LIVE_LINE=false

# ---------------------------------------------------------------------------
# Cleanup + signals
# ---------------------------------------------------------------------------
cleanup() { rm -f "$INCIDENT_FILE"; }
trap cleanup EXIT

handle_shutdown() {
    [[ "$ON_LIVE_LINE" == true ]] && { echo; ON_LIVE_LINE=false; }
    echo
    print_line "${DIM}[INFO] Stopped by user (Ctrl+C)${RESET}"
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

strip_ansi() { sed 's/\x1b\[[0-9;]*m//g'; }

print_line() {
    local msg="$1"
    [[ "$ON_LIVE_LINE" == true ]] && { echo; ON_LIVE_LINE=false; }
    local ts
    ts=$(date '+%Y-%m-%d %H:%M:%S')
    local out="[${ts}] ${msg}"
    echo -e "$out"
    if [[ -n "$LOG_FILE" ]]; then
        echo -e "$out" | strip_ansi >> "$LOG_FILE" 2>/dev/null || true
    fi
}

print_sub() {
    local msg="$1"
    [[ "$ON_LIVE_LINE" == true ]] && { echo; ON_LIVE_LINE=false; }
    local out="            ${msg}"
    echo -e "$out"
    if [[ -n "$LOG_FILE" ]]; then
        echo -e "$out" | strip_ansi >> "$LOG_FILE" 2>/dev/null || true
    fi
}

live_line() {
    printf "\r  %b   " "$1"
    ON_LIVE_LINE=true
}

separator() {
    [[ "$ON_LIVE_LINE" == true ]] && { echo; ON_LIVE_LINE=false; }
    local line
    line=$(printf '─%.0s' {1..58})
    echo -e "  ${DIM}${line}${RESET}"
    if [[ -n "$LOG_FILE" ]]; then
        echo "  ${line}" | strip_ansi >> "$LOG_FILE" 2>/dev/null || true
    fi
}

fmt_short() {
    local secs=$1
    local h=$(( secs / 3600 ))
    local m=$(( (secs % 3600) / 60 ))
    local s=$(( secs % 60 ))
    if   (( h > 0 )); then printf "%dh %dm %ds" "$h" "$m" "$s"
    elif (( m > 0 )); then printf "%dm %ds" "$m" "$s"
    else                   printf "%ds" "$s"
    fi
}

fmt_long() {
    local secs=$1
    local h=$(( secs / 3600 ))
    local m=$(( (secs % 3600) / 60 ))
    local s=$(( secs % 60 ))
    local out=""
    (( h > 0 )) && out+="${h} hour$([[ $h -ne 1 ]] && echo s), "
    (( m > 0 )) && out+="${m} minute$([[ $m -ne 1 ]] && echo s), "
    out+="${s} second$([[ $s -ne 1 ]] && echo s)"
    echo "$out"
}

# ---------------------------------------------------------------------------
# Check — sets LAST_RTT (integer ms, or empty on failure), echoes UP/DOWN
# ---------------------------------------------------------------------------
do_check() {
    LAST_RTT=""
    if [[ -n "$PORT" ]]; then
        local start_ns end_ns
        start_ns=$(date +%s%N 2>/dev/null) || start_ns=0
        if (timeout 2 bash -c "echo >/dev/tcp/${TARGET}/${PORT}") >/dev/null 2>&1; then
            if [[ "$start_ns" != "0" ]]; then
                end_ns=$(date +%s%N 2>/dev/null) || end_ns=0
                [[ "$end_ns" != "0" ]] && LAST_RTT=$(( (end_ns - start_ns) / 1000000 ))
            fi
            echo "UP"
        else
            echo "DOWN"
        fi
    else
        local output
        output=$(ping -c 1 -W 2 "$TARGET" 2>/dev/null)
        if [[ $? -eq 0 ]]; then
            local raw_rtt
            raw_rtt=$(echo "$output" | grep -oE 'time[=<][0-9.]+' | grep -oE '[0-9.]+' | head -1)
            if [[ -n "$raw_rtt" ]]; then
                LAST_RTT=$(printf "%.0f" "$raw_rtt" 2>/dev/null) || LAST_RTT=""
            fi
            echo "UP"
        else
            echo "DOWN"
        fi
    fi
}

check_label() {
    if [[ -n "$PORT" ]]; then echo "TCP:${PORT}"; else echo "ICMP"; fi
}

# ---------------------------------------------------------------------------
# RTT alert check — called after each successful UP check
# ---------------------------------------------------------------------------
check_rtt_alert() {
    [[ -z "$ALERT_RTT" || -z "$LAST_RTT" ]] && return
    if (( LAST_RTT > ALERT_RTT )); then
        if [[ "$RTT_OVER_LIMIT" == false ]]; then
            RTT_OVER_LIMIT=true
            RTT_ALERT_COUNT=$(( RTT_ALERT_COUNT + 1 ))
            print_line "${YELLOW}${BOLD}[ SLOW ]${RESET}  RTT spike: ${YELLOW}${LAST_RTT}ms${RESET} exceeds ${YELLOW}${ALERT_RTT}ms${RESET} threshold"
        fi
    else
        if [[ "$RTT_OVER_LIMIT" == true ]]; then
            RTT_OVER_LIMIT=false
            print_line "${GREEN}${BOLD}[  OK  ]${RESET}  RTT back to normal: ${GREEN}${LAST_RTT}ms${RESET}"
        fi
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
    print_line "  Target          : ${WHITE}${TARGET}${RESET}"
    print_line "  Check Method    : ${WHITE}$(check_label)${RESET}"
    print_line "  Session Started : ${WHITE}${SESSION_START}${RESET}"
    print_line "  Ping Interval   : ${WHITE}${INTERVAL}s${RESET}"
    [[ -n "$ALERT_RTT" ]] && print_line "  RTT Alert       : ${YELLOW}${ALERT_RTT}ms${RESET}"
    [[ -n "$LOG_FILE"  ]] && print_line "  Log File        : ${WHITE}${LOG_FILE}${RESET}"
    echo -e "${BOLD}${CYAN}$(printf -- '-%.0s' $(seq 1 $w))${RESET}"
    echo
}

# ---------------------------------------------------------------------------
# Final summary on exit
# ---------------------------------------------------------------------------
print_summary() {
    local now_epoch
    now_epoch=$(date +%s)
    local session_secs=$(( now_epoch - SESSION_START_EPOCH ))

    local loss_pct="0.0"
    if (( PING_COUNT > 0 )); then
        local failed=$(( PING_COUNT - PING_SUCCESS ))
        loss_pct=$(awk "BEGIN { printf \"%.1f\", ($failed / $PING_COUNT) * 100 }")
    fi

    echo
    echo -e "${BOLD}${CYAN}$(printf '=%.0s' $(seq 1 60))${RESET}"
    echo -e "${BOLD}${WHITE}  SESSION SUMMARY${RESET}"
    echo -e "${BOLD}${CYAN}$(printf '=%.0s' $(seq 1 60))${RESET}"
    print_line "  Session Duration : $(fmt_long "$session_secs")"
    print_line "  Checks Sent      : ${PING_COUNT}"
    print_line "  Packet Loss      : ${loss_pct}%"
    if [[ -n "$ALERT_RTT" ]]; then
        print_line "  RTT Alerts       : ${RTT_ALERT_COUNT} spike(s) above ${ALERT_RTT}ms"
    fi
    echo

    if [[ ! -s "$INCIDENT_FILE" ]]; then
        print_line "${GREEN}${BOLD}  No downtime detected — host was UP the entire session.${RESET}"
    else
        INCIDENT_COUNT=$(wc -l < "$INCIDENT_FILE")
        print_line "${YELLOW}  Downtime Events  : ${INCIDENT_COUNT}${RESET}"
        print_line "${YELLOW}  Total Time DOWN  : $(fmt_long "$TOTAL_DOWNTIME")${RESET}"
        echo
        echo -e "${BOLD}  Incident Log:${RESET}"
        echo -e "${DIM}  $(printf -- '-%.0s' $(seq 1 56))${RESET}"

        local idx=0
        while IFS='|' read -r lost_ts restored_ts dur_secs; do
            idx=$(( idx + 1 ))
            echo
            print_sub "${BOLD}Incident #${idx}${RESET}"
            print_sub "  Went DOWN  : ${RED}${lost_ts}${RESET}"
            print_sub "  Came UP    : ${GREEN}${restored_ts}${RESET}"
            print_sub "  Down for   : ${YELLOW}$(fmt_long "$dur_secs")${RESET}"
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

Continuously monitor network connectivity to a host.
Shows when it goes down, for how long, and when it comes back up.

Arguments:
  TARGET                IP address or hostname to monitor

Options:
  -i, --interval SEC    seconds between checks (default: 2, minimum: 1)
  -p, --port PORT       TCP port to check instead of ICMP ping
  -l, --log FILE        append plain-text log to FILE
      --alert-rtt MS    alert when RTT exceeds this threshold in milliseconds
      --no-color        disable ANSI color output
  -v, --version         print version and exit
  -h, --help            print this help and exit

Examples:
  checkup.sh 8.8.8.8
  checkup.sh 10.20.20.10 --interval 1
  checkup.sh google.com --port 443
  checkup.sh 192.168.1.1 --port 22 --interval 2 --log uptime.log
  checkup.sh 8.8.8.8 --alert-rtt 100
EOF
}

parse_args() {
    if (( $# == 0 )); then print_usage; exit 1; fi

    for arg in "$@"; do
        case "$arg" in
            -h|--help)    print_usage; exit 0 ;;
            -v|--version) echo "checkup $VERSION"; exit 0 ;;
        esac
    done

    TARGET="$1"; shift

    while (( $# > 0 )); do
        case "$1" in
            -i|--interval)  INTERVAL="${2:?'--interval requires a value'}"; shift 2 ;;
            -p|--port)      PORT="${2:?'--port requires a value'}"; shift 2 ;;
            -l|--log)       LOG_FILE="${2:?'--log requires a value'}"; shift 2 ;;
            --alert-rtt)    ALERT_RTT="${2:?'--alert-rtt requires a value'}"; shift 2 ;;
            --no-color)     disable_color; shift ;;
            *) echo "Unknown option: $1" >&2; print_usage; exit 1 ;;
        esac
    done

    if (( INTERVAL < 1 )); then
        echo "Error: --interval must be >= 1 second" >&2; exit 1
    fi
    if [[ -n "$ALERT_RTT" ]] && ! [[ "$ALERT_RTT" =~ ^[0-9]+$ ]]; then
        echo "Error: --alert-rtt must be a positive integer (milliseconds)" >&2; exit 1
    fi
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
main() {
    parse_args "$@"
    [[ -n "$LOG_FILE" ]] && : >> "$LOG_FILE"
    : > "$INCIDENT_FILE"

    SESSION_START=$(date '+%Y-%m-%d %H:%M:%S')
    SESSION_START_EPOCH=$(date +%s)

    print_header

    # First check — establish baseline
    STATE=$(do_check)
    PING_COUNT=$(( PING_COUNT + 1 ))

    if [[ "$STATE" == "UP" ]]; then
        PING_SUCCESS=$(( PING_SUCCESS + 1 ))
        UPTIME_START_EPOCH=$(date +%s)
        local rtt_str=""
        [[ -n "$LAST_RTT" ]] && rtt_str="  (RTT: ${LAST_RTT}ms)"
        print_line "${GREEN}${BOLD}[  UP  ]${RESET}  Host is ${GREEN}ALIVE${RESET}${rtt_str}"
        check_rtt_alert
    else
        DOWNTIME_START_TS=$(date '+%Y-%m-%d %H:%M:%S')
        DOWNTIME_START_EPOCH=$(date +%s)
        separator
        print_line "${RED}${BOLD}[ DOWN ]${RESET}  Host is ${RED}UNREACHABLE${RESET}"
        print_sub  "  Down since : ${RED}${DOWNTIME_START_TS}${RESET}"
        separator
    fi

    # Monitoring loop
    while true; do
        sleep "$INTERVAL"

        local new_state now now_epoch
        new_state=$(do_check)
        now=$(date '+%Y-%m-%d %H:%M:%S')
        now_epoch=$(date +%s)

        PING_COUNT=$(( PING_COUNT + 1 ))
        [[ "$new_state" == "UP" ]] && PING_SUCCESS=$(( PING_SUCCESS + 1 ))

        # UP → DOWN
        if [[ "$STATE" == "UP" && "$new_state" == "DOWN" ]]; then
            DOWNTIME_START_TS="$now"
            DOWNTIME_START_EPOCH="$now_epoch"
            UPTIME_START_EPOCH=0
            RTT_OVER_LIMIT=false
            echo
            separator
            print_line "${RED}${BOLD}[ DOWN ]${RESET}  Host went ${RED}UNREACHABLE${RESET}"
            print_sub  "  Down since : ${RED}${DOWNTIME_START_TS}${RESET}"
            separator

        # DOWN → UP
        elif [[ "$STATE" == "DOWN" && "$new_state" == "UP" ]]; then
            local dur=$(( now_epoch - DOWNTIME_START_EPOCH ))
            TOTAL_DOWNTIME=$(( TOTAL_DOWNTIME + dur ))
            echo
            separator
            print_line "${GREEN}${BOLD}[  UP  ]${RESET}  Host is ${GREEN}BACK ONLINE${RESET}"
            print_sub  "  Came back  : ${GREEN}${now}${RESET}"
            print_sub  "  Was down   : ${RED}${DOWNTIME_START_TS}${RESET}  →  ${GREEN}${now}${RESET}"
            print_sub  "  Total down : ${YELLOW}$(fmt_long "$dur")${RESET}"
            separator
            echo
            UPTIME_START_EPOCH="$now_epoch"
            echo "${DOWNTIME_START_TS}|${now}|${dur}" >> "$INCIDENT_FILE"
            check_rtt_alert

        # Steady UP — live ticker with RTT and optional alert indicator
        elif [[ "$STATE" == "UP" && "$new_state" == "UP" ]]; then
            check_rtt_alert
            local rtt_str="" up_for="" alert_str=""
            [[ -n "$LAST_RTT" ]] && rtt_str="  (RTT: ${LAST_RTT}ms)"
            if (( UPTIME_START_EPOCH > 0 )); then
                up_for="  up $(fmt_short $(( now_epoch - UPTIME_START_EPOCH )))"
            fi
            if [[ "$RTT_OVER_LIMIT" == true && -n "$ALERT_RTT" ]]; then
                alert_str="${YELLOW}  ⚠ >${ALERT_RTT}ms${RESET}"
            fi
            live_line "${GREEN}●${RESET}  ${now}  Host is ${GREEN}ALIVE${RESET}${rtt_str}${DIM}${up_for}${RESET}${alert_str}"

        # Steady DOWN — elapsed counter
        elif [[ "$STATE" == "DOWN" && "$new_state" == "DOWN" ]]; then
            local elapsed=$(( now_epoch - DOWNTIME_START_EPOCH ))
            live_line "${RED}✗${RESET}  ${now}  Still ${RED}DOWN${RESET} — $(fmt_short "$elapsed")"
        fi

        STATE="$new_state"
    done
}

main "$@"
