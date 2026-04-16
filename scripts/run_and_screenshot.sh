#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/run_and_screenshot.sh
    # Runs KaTrain Qt (default), writes screenshots/_katrain_last.png

  scripts/run_and_screenshot.sh test_button.py
    # Runs "uv run python test_button.py"

  scripts/run_and_screenshot.sh --out screenshots/foo.png -- uv run python -m katrain
    # Runs an arbitrary command (everything after --), screenshots its window

Options:
  --out PATH     Output path for the screenshot (default: screenshots/_katrain_last.png)
  --help         Show help

Notes:
  - macOS requires Screen Recording permission for your terminal/IDE to take screenshots.
  - This script finds the window by matching the owning PID (and descendants) rather than window title.
EOF
}

OUT="screenshots/_katrain_last.png"

CMD_MODE="default"
CMD=()

while [ $# -gt 0 ]; do
  case "$1" in
    --out)
      OUT="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --)
      shift
      CMD_MODE="cmd"
      CMD=("$@")
      break
      ;;
    *.py)
      CMD_MODE="py"
      CMD=("uv" "run" "python" "$1")
      shift
      if [ $# -gt 0 ]; then
        echo "Unexpected extra args after python file. Use -- for arbitrary commands." >&2
        exit 2
      fi
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ "$CMD_MODE" = "default" ]; then
  CMD=("uv" "run" "katrain")
fi

mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"

RUN_PID=""

cleanup() {
  if [ -n "${RUN_PID:-}" ]; then
    kill "$RUN_PID" 2>/dev/null || true
    # Don't hang forever if the app ignores SIGTERM.
    for _ in $(seq 1 30); do
      if ! kill -0 "$RUN_PID" 2>/dev/null; then
        break
      fi
      sleep 0.2
    done
    kill -KILL "$RUN_PID" 2>/dev/null || true
    wait "$RUN_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

"${CMD[@]}" >/tmp/run_and_screenshot_stdout.log 2>/tmp/run_and_screenshot_stderr.log &
RUN_PID=$!

descendants() {
  # Print all descendant pids of $1 (best-effort).
  local root="$1"
  local seen=" $root "
  local queue="$root"
  local next_queue=""
  local p=""
  local child=""

  # Avoid bash array/nounset edge cases; use whitespace-separated queues.
  while [ -n "${queue:-}" ]; do
    next_queue=""
    for p in $queue; do
      while read -r child; do
        if [ -z "${child:-}" ]; then
          continue
        fi
        case "$seen" in
          *" $child "*) ;;
          *)
            echo "$child"
            seen="$seen$child "
            next_queue="$next_queue $child"
            ;;
        esac
      done < <(pgrep -P "$p" 2>/dev/null || true)
    done
    queue="${next_queue# }"
  done
}

WID=""
for _ in $(seq 1 80); do
  # Include descendants because wrappers (like uv) may not own the window.
  PIDS=("$RUN_PID")
  while read -r p; do
    PIDS+=("$p")
  done < <(descendants "$RUN_PID" || true)

  WID="$(
    swift -e '
import Cocoa
let pids = Set(CommandLine.arguments.dropFirst().compactMap { Int($0) })
let windows = CGWindowListCopyWindowInfo(.optionOnScreenOnly, kCGNullWindowID) as? [[String: Any]] ?? []
for w in windows {
  let pid = (w[kCGWindowOwnerPID as String] as? Int) ?? -1
  if !pids.contains(pid) { continue }
  let layer = (w[kCGWindowLayer as String] as? Int) ?? 0
  if layer != 0 { continue }
  let wid = (w[kCGWindowNumber as String] as? Int) ?? 0
  if wid != 0 { print(wid); break }
}
' "${PIDS[@]}" 2>/dev/null
  )"

  if [ -n "${WID:-}" ]; then
    break
  fi
  sleep 0.2
done

if [ -z "${WID:-}" ]; then
  echo "Could not find a window-id for pid=$RUN_PID (or descendants)." >&2
  echo "If this is macOS privacy related, grant Screen Recording permission to your terminal/IDE." >&2
  echo "See /tmp/run_and_screenshot_stderr.log for app startup errors." >&2
  exit 2
fi

# Give the UI a moment to render the first frame.
sleep 1
screencapture -x -o -l "$WID" "$OUT"

echo "Wrote: $OUT"
