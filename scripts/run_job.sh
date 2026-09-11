#!/usr/bin/env bash
# Run under nohup. The job directory holds a durable PID, attempts and exit code.
set -euo pipefail
if [[ $# -lt 2 ]]; then
    echo "Usage: $0 JOB_DIR INPUT_ROOT [--files PATH] [--endpoint URL]" >&2
    exit 2
fi
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
job_dir=$1
shift
mkdir -p -- "$job_dir"
job_dir=$(cd -- "$job_dir" && pwd)
exec 9>"$job_dir/job.lock"
if ! flock -n 9; then
    echo "This job already has a running supervisor." >&2
    exit 1
fi
python_bin=${PDF_CLIENT_PYTHON:-/workspace/.venv-qwen38-client/bin/python}
if [[ ! -x "$python_bin" ]]; then
    echo "Missing client Python: $python_bin. Set PDF_CLIENT_PYTHON." >&2
    exit 2
fi
printf '%s\n' "$$" > "$job_dir/supervisor.pid"
rm -f -- "$job_dir/exit.code"
child_pid=
finish() {
    printf '%s\n' "$1" > "$job_dir/exit.code.tmp"
    mv -- "$job_dir/exit.code.tmp" "$job_dir/exit.code"
}
interrupt() {
    trap '' INT TERM
    if [[ -n "$child_pid" ]]; then
        kill -TERM "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
    fi
    finish 130
    exit 130
}
trap interrupt INT TERM
for attempt in 1 2 3; do
    printf '%s\n' "$attempt" > "$job_dir/attempt"
    echo "Starting V15 attempt $attempt/3 at $(date -u +%FT%TZ)"
    "$python_bin" "$script_dir/../run_production.py" "$@" &
    child_pid=$!
    printf '%s\n' "$child_pid" > "$job_dir/worker.pid"
    code=0
    wait "$child_pid" || code=$?
    child_pid=
    if [[ "$code" -eq 0 || "$code" -ne 1 || "$attempt" -eq 3 ]]; then
        finish "$code"
        exit "$code"
    fi
    echo "Attempt failed; resuming validated checkpoints in 15 seconds."
    sleep 15
done
