import unittest
import tempfile
import os
import shutil
from utils.log_watcher import LogWatcher

class TestLogWatcher(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.log_path = os.path.join(self.test_dir, "test.log")

        # Create a dummy log file
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write("Line 1\nLine 2\n")

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)

    def test_init_starts_at_end(self):
        watcher = LogWatcher(self.log_path)
        # First call initializes and consumes nothing
        new_lines = watcher.read_new_lines()
        self.assertEqual(new_lines, [])

        # Append new data
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write("Line 3\n")

        new_lines = watcher.read_new_lines()
        self.assertEqual(new_lines, ["Line 3"])

    def test_read_multiple_lines(self):
        watcher = LogWatcher(self.log_path)
        watcher.read_new_lines() # Init

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write("Line 3\nLine 4\n")

        new_lines = watcher.read_new_lines()
        self.assertEqual(new_lines, ["Line 3", "Line 4"])

    def test_rotation(self):
        watcher = LogWatcher(self.log_path)
        watcher.read_new_lines() # Init

        # Simulate rotation (overwrite with smaller content)
        with open(self.log_path, "w", encoding="utf-8") as f:
            f.write("New Start\n")

        new_lines = watcher.read_new_lines()
        self.assertEqual(new_lines, ["New Start"])

    def test_missing_file(self):
        missing_path = os.path.join(self.test_dir, "missing.log")
        watcher = LogWatcher(missing_path)
        self.assertEqual(watcher.read_new_lines(), [])

        # Create it later
        with open(missing_path, "w", encoding="utf-8") as f:
            f.write("Created now\n")

        # First read after creation should skip existing content (init logic)
        self.assertEqual(watcher.read_new_lines(), [])

        with open(missing_path, "a", encoding="utf-8") as f:
            f.write("Appended\n")

        self.assertEqual(watcher.read_new_lines(), ["Appended"])
