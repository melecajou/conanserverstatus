import os
import logging
import asyncio
from typing import List


class LogWatcher:
    """
    Watches a log file for new lines.
    Handles file rotation (when size shrinks) and tracks the read position.
    """

    def __init__(self, file_path: str, tail_bytes: int = 0, max_read_bytes: int = 2 * 1024 * 1024):
        """
        Args:
            file_path: Path to the log file.
            tail_bytes: If > 0, the watcher will start reading from this many bytes
                        before the end of the file on the first call.
            max_read_bytes: The maximum number of bytes to read in a single call.
                            Defaults to 2MB to prevent memory exhaustion (DoS).
        """
        self.file_path = file_path
        self._last_pos = 0
        self._initialized = False
        self._tail_bytes = tail_bytes
        self._max_read_bytes = max_read_bytes

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
            # Open in binary mode to safely handle seeking and reading chunks
            with open(self.file_path, "rb") as f:
                f.seek(self._last_pos)

                # Read at most max_read_bytes to prevent DoS
                chunk = f.read(self._max_read_bytes)

                if not chunk:
                    return []

                # Find the last newline to ensure we process complete lines only
                last_newline = chunk.rfind(b'\n')

                if last_newline != -1:
                    # We found a newline. Process up to it.
                    valid_chunk = chunk[:last_newline + 1]
                    self._last_pos += len(valid_chunk)

                    # Decode and split (ignoring errors to match legacy behavior)
                    try:
                        content_str = valid_chunk.decode("utf-8", errors="ignore")
                        lines = content_str.splitlines()
                    except Exception as e:
                        logging.error(f"Error decoding log chunk from {self.file_path}: {e}")
                        lines = []
                else:
                    # No newline found in the chunk.
                    if len(chunk) < self._max_read_bytes:
                         # We reached EOF without a newline.
                         # This is a partial line at the end of file.
                         # We should wait for more data (do not advance cursor).
                         return []
                    else:
                         # The chunk is full size but has no newline.
                         # This is a generic "Line too long" case.
                         # We skip it to protect memory.
                         self._last_pos += len(chunk)
                         logging.warning(f"LogWatcher: skipped {len(chunk)} bytes in {self.file_path} (line too long)")
                         return []

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
