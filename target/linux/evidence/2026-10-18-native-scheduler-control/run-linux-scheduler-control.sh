#!/usr/bin/env bash
set -euo pipefail

root=/tmp/holy-crap-native-scheduler-control
raw="$root/raw"
logs="$root/logs"
metadata="$root/metadata"
mkdir -p "$raw" "$logs" "$metadata"

# Keep every child under the same 8 GiB virtual address-space ceiling used by
# the application benchmarks. The timing and stress binaries use far less.
ulimit -v 8388608

benchmark="$root/wakeup_jitter_bench"
stress="$root/bounded_cpu_stress"

capture_host_metadata() {
  {
    echo "captured_at=$(date -Iseconds)"
    uname -a
    printf 'online_cpus='; cat /sys/devices/system/cpu/online
    printf 'isolated_cpus='; cat /sys/devices/system/cpu/isolated 2>/dev/null || true
    printf 'kernel_cmdline='; tr '\000' ' ' </proc/cmdline; echo
    printf 'clocksource_current='; cat /sys/devices/system/clocksource/clocksource0/current_clocksource
    printf 'clocksource_available='; cat /sys/devices/system/clocksource/clocksource0/available_clocksource
    printf 'loadavg='; cat /proc/loadavg
    printf 'uptime='; cat /proc/uptime
    printf 'memory='; grep -E '^(MemTotal|MemAvailable|SwapTotal|SwapFree):' /proc/meminfo
    printf 'rt_runtime_us='; cat /proc/sys/kernel/sched_rt_runtime_us
    printf 'rt_period_us='; cat /proc/sys/kernel/sched_rt_period_us
    printf 'shell_limits_begin\n'; ulimit -a; printf 'shell_limits_end\n'
    printf 'cpu_governors_begin\n'
    for f in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do printf '%s=' "$f"; cat "$f"; done
    printf 'cpu_governors_end\n'
    printf 'cpu_info_begin\n'; lscpu; printf 'cpu_info_end\n'
    printf 'process_snapshot_begin\n'
    ps -eo pid,psr,cls,rtprio,pri,ni,pcpu,pmem,rss,vsz,etimes,comm,args --sort=-pcpu
    printf 'process_snapshot_end\n'
  } >"$metadata/host.txt"
  if command -v vcgencmd >/dev/null 2>&1; then
    vcgencmd measure_temp >"$metadata/thermal-before.txt" 2>&1 || true
    vcgencmd get_throttled >"$metadata/throttled-before.txt" 2>&1 || true
  fi
}

capture_process_metadata() {
  local pid=$1 prefix=$2
  {
    echo "captured_at=$(date -Iseconds)"
    ps -p "$pid" -o pid,ppid,psr,cls,rtprio,pri,ni,pcpu,pmem,rss,vsz,etimes,comm,args || true
    printf 'affinity='; taskset -pc "$pid" 2>&1 || true
    printf 'status_begin\n'; cat "/proc/$pid/status" 2>/dev/null || true; printf 'status_end\n'
    printf 'limits_begin\n'; cat "/proc/$pid/limits" 2>/dev/null || true; printf 'limits_end\n'
    printf 'sched_begin\n'; cat "/proc/$pid/sched" 2>/dev/null || true; printf 'sched_end\n'
  } >"$metadata/$prefix-process.txt"
}

run_trial() {
  local scenario=$1 trial=$2 fixed=$3 load_spec=$4
  local prefix="jitter-$scenario-trial$trial"
  local -a load_pids=()
  local cpu

  if [[ -n "$load_spec" ]]; then
    IFS=',' read -ra cpus <<<"$load_spec"
    for cpu in "${cpus[@]}"; do
      taskset -c "$cpu" "$stress" 6.5 >"$logs/$prefix-cpu$cpu.out" 2>"$logs/$prefix-cpu$cpu.err" &
      load_pids+=("$!")
    done
    sleep 0.25
  fi

  local -a command=(taskset -c 3 "$benchmark" 5000 1000 100 "$raw/$prefix.csv")
  if [[ "$fixed" == true ]]; then
    command=(sudo -n chrt -f 40 taskset -c 3 "$benchmark" 5000 1000 100 "$raw/$prefix.csv")
  fi

  local started finished rc
  started=$(date +%s%N)
  set +e
  "${command[@]}" >"$raw/$prefix.json" 2>"$logs/$prefix.err" &
  local bench_pid=$!
  sleep 0.5
  capture_process_metadata "$bench_pid" "$prefix"
  wait "$bench_pid"
  rc=$?
  set -e
  finished=$(date +%s%N)

  if [[ -s "$raw/$prefix.json" ]]; then
    sed -i 's/"tool":"qnx_jitter_bench"/"tool":"wakeup_jitter_bench"/' "$raw/$prefix.json"
  fi
  {
    echo "scenario=$scenario"
    echo "trial=$trial"
    echo "fixed_priority_requested=$fixed"
    echo "load_cpus=$load_spec"
    echo "benchmark_cpu=3"
    echo "returncode=$rc"
    echo "started_epoch_ns=$started"
    echo "finished_epoch_ns=$finished"
    echo "duration_ns=$((finished-started))"
  } >"$metadata/$prefix-run.txt"

  local load_pid
  for load_pid in "${load_pids[@]}"; do
    wait "$load_pid" || true
  done
  if [[ "$rc" -ne 0 ]]; then
    echo "trial failed: $prefix rc=$rc" >&2
    return "$rc"
  fi
}

capture_host_metadata

scenarios=(
  'idle-default false '
  'idle-fifo40 true '
  'cross-core-load-default false 0,1,2'
  'cross-core-load-fifo40 true 0,1,2'
  'same-core-load-default false 3'
  'same-core-load-fifo40 true 3'
)

for spec in "${scenarios[@]}"; do
  read -r scenario fixed load_spec <<<"$spec"
  for trial in 1 2 3 4 5; do
    run_trial "$scenario" "$trial" "$fixed" "${load_spec:-}"
  done
done

if command -v vcgencmd >/dev/null 2>&1; then
  vcgencmd measure_temp >"$metadata/thermal-after.txt" 2>&1 || true
  vcgencmd get_throttled >"$metadata/throttled-after.txt" 2>&1 || true
fi
date -Iseconds >"$metadata/completed-at.txt"
