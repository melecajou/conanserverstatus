import time
import os
import sys
import re
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.log_parser import parse_log_lines, STATUS_REPORT_RE, VERSION_RE

def original_parse_log_lines(lines, current_stats=None):
    stats = current_stats.copy() if current_stats else {}
    if not lines:
        return stats
    try:
        log_content = "\n".join(lines)
        status_reports = re.findall(
            r"LogServerStats: Status report\. Uptime=(\d+).*? Mem=\d+:\d+:(\d+):\d+.*? CPU=([\d\.]+).*? Players=(\d+).*? FPS=([\d\.:]+)",
            log_content,
        )
        if status_reports:
            last_report = status_reports[-1]
            uptime_seconds = int(last_report[0])
            days, rem = divmod(uptime_seconds, 86400)
            hours, rem = divmod(rem, 3600)
            minutes, _ = divmod(rem, 60)
            stats["uptime"] = f"{days}d {hours}h {minutes}m"
            memory_b = int(last_report[1])
            stats["memory"] = f"{memory_b / (1024**3):.2f} GB"
            stats["cpu"] = f"{float(last_report[2]):.1f}%"
            stats["players"] = last_report[3]
            fps_parts = last_report[4].split(":")
            frame_time = float(fps_parts[1] if len(fps_parts) > 1 else fps_parts[0])
            if frame_time > 0:
                stats["fps"] = f"{1000.0 / frame_time:.1f}"
            else:
                stats["fps"] = "0.0"

        version_match = re.search(
            r"LogInit: Engine Version: (.*?)$", log_content, re.MULTILINE
        )
        if version_match:
            stats["version"] = version_match.group(1).strip()
    except Exception as e:
        pass
    return stats

def run_benchmark():
    # Generate some fake log lines
    lines = []
    # Make it bigger to see the difference clearly
    for i in range(100000):
        lines.append(f"Some random log line {i}")
        if i % 100 == 0:
            lines.append(f"LogServerStats: Status report. Uptime={1000+i} Mem=1:2:3:4 CPU=10.5 Players=20 FPS=10:16.6:20")
        if i % 500 == 0:
            lines.append(f"LogInit: Engine Version: 4.27.2-{i}")

    print(f"Generated {len(lines)} log lines.")

    start_time = time.perf_counter()
    for _ in range(20):
        stats_orig = original_parse_log_lines(lines)
    end_time = time.perf_counter()
    print(f"Original unoptimized parse_log_lines (no cache): {end_time - start_time:.4f} seconds")

    start_time = time.perf_counter()
    for _ in range(20):
        stats_opt = parse_log_lines(lines)
    end_time = time.perf_counter()
    print(f"Optimized parse_log_lines (no cache): {end_time - start_time:.4f} seconds")

    start_time = time.perf_counter()
    for _ in range(20):
        stats_orig = original_parse_log_lines(lines, current_stats={"version": "4.27.2-0"})
    end_time = time.perf_counter()
    print(f"Original unoptimized parse_log_lines (with cache): {end_time - start_time:.4f} seconds")

    start_time = time.perf_counter()
    for _ in range(20):
        stats_opt = parse_log_lines(lines, current_stats={"version": "4.27.2-0"})
    end_time = time.perf_counter()
    print(f"Optimized parse_log_lines (with cache): {end_time - start_time:.4f} seconds")

if __name__ == '__main__':
    run_benchmark()
