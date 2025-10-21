import re
import logging
import os
from typing import Dict

def parse_server_log(log_path: str) -> Dict[str, str]:
    """Parses the server log file to extract system stats."""
    stats = {}
    if not log_path or not os.path.exists(log_path):
        return stats

    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()[-500:]
            log_content = "".join(lines)

            # Uptime, CPU, Players, FPS from LogServerStats
            status_reports = re.findall(r"LogServerStats: Status report\. Uptime=(\d+).*? Mem=\d+:\d+:(\d+):\d+.*? CPU=([\d\.]+).*? Players=(\d+).*? FPS=([\d\.]+)", log_content)
            if status_reports:
                last_report = status_reports[-1]
                uptime_seconds = int(last_report[0])
                days, rem = divmod(uptime_seconds, 86400)
                hours, rem = divmod(rem, 3600)
                minutes, _ = divmod(rem, 60)
                stats['uptime'] = f"{days}d {hours}h {minutes}m"
                
                memory_b = int(last_report[1])
                stats['memory'] = f"{memory_b / (1024**3):.2f} GB"

                stats['cpu'] = f"{float(last_report[2]):.1f}%"
                stats['players'] = last_report[3]
                stats['fps'] = f"{float(last_report[4]):.1f}"

            # Game Version from LogInit
            version_match = re.search(r"LogInit: Engine Version: (.*?)$", log_content, re.MULTILINE)
            if version_match:
                stats['version'] = version_match.group(1).strip()

    except Exception as e:
        logging.warning(f"Could not parse log file {log_path}: {e}")
    
    return stats
