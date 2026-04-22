import re
import logging
from typing import Dict, List, Optional

# Precompiled regular expressions for parsing log entries
STATUS_REPORT_RE = re.compile(
    r"LogServerStats: Status report\. Uptime=(\d+).*? Mem=\d+:\d+:(\d+):\d+.*? CPU=([\d\.]+).*? Players=(\d+).*? FPS=([\d\.:]+)"
)
VERSION_RE = re.compile(r"LogInit: Engine Version: (.*?)$", re.MULTILINE)

def parse_log_lines(
    lines: List[str], current_stats: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """
    Parses a list of log lines to extract system stats, updating the provided stats dictionary.

    Args:
        lines: A list of new log lines.
        current_stats: The existing stats dictionary to update.

    Returns:
        A new dictionary with updated stats.
    """
    stats = current_stats.copy() if current_stats else {}

    if not lines:
        return stats

    try:
        log_content = "\n".join(lines)

        # Uptime, CPU, Players, FPS from LogServerStats
        status_reports = STATUS_REPORT_RE.findall(log_content)
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

            # FPS values in log are actually frame times in ms. Real FPS = 1000 / frame_time.
            # Format is min:avg:max, we want avg (index 1)
            fps_parts = last_report[4].split(":")
            frame_time = float(fps_parts[1] if len(fps_parts) > 1 else fps_parts[0])
            if frame_time > 0:
                stats["fps"] = f"{1000.0 / frame_time:.1f}"
            else:
                stats["fps"] = "0.0"

        # Game Version from LogInit
        if "version" not in stats:
            version_match = VERSION_RE.search(log_content)
            if version_match:
                stats["version"] = version_match.group(1).strip()

    except Exception as e:
        logging.warning(f"Error parsing log lines: {e}")

    return stats
