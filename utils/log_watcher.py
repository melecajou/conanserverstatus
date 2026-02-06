import os
import logging
import asyncio
from typing import List


class LogWatcher:
    """
    Watches a log file for new lines.
    Handles file rotation (when size shrinks) and tracks the read position.
    """

    def __init__(self, file_path: str, tail_bytes: int = 0):
        """
        Args:
            file_path: Path to the log file.
            tail_bytes: If > 0, the watcher will start reading from this many bytes
                        before the end of the file on the first call.
        """
        self.file_path = file_path
        self._last_pos = 0
        self._initialized = False
        self._tail_bytes = tail_bytes

    def _read_file_sync(self) -> List[str]:
        """
        Synchronous method to perform file I/O operations.
        This runs in a separate thread.
        """
        if not self.file_path or not os.path.exists(self.file_path):
            return []

        try:
            current_size = os.path.getsize(self.file_path)

            # Initialize cursor
            if not self._initialized:
                if self._tail_bytes > 0:
                    self._last_pos = max(0, current_size - self._tail_bytes)
                else:
                    self._last_pos = current_size

                self._initialized = True

                # If NOT tailing, we stop here (standard cursor behavior)
                # If tailing, we continue to read the tail immediately
                if self._tail_bytes == 0:
                    return []

            # Check for rotation (file got smaller)
            if current_size < self._last_pos:
                self._last_pos = 0

            # No new data
            if current_size == self._last_pos:
                return []

            lines = []
            with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._last_pos)
                new_content = f.read()
                self._last_pos = f.tell()

                if new_content:
                    lines = new_content.splitlines()

            return lines

        except Exception as e:
            logging.error(f"Error reading log {self.file_path}: {e}")
            return []

    async def read_new_lines(self) -> List[str]:
        """
        Reads new lines appended to the log file since the last check asynchronously.
        Offloads blocking I/O to a thread.

        Returns:
            A list of new strings (lines).
        """
        return await asyncio.to_thread(self._read_file_sync)
