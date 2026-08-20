#!/usr/bin/env python3
"""Tests for concurrent pipe draining and wall-clock process timeouts."""

import subprocess
import sys
import time
import unittest

from process_runner import run_streaming_process


class TestStreamingProcess(unittest.TestCase):
    def test_drains_stderr_while_streaming_stdout(self):
        lines = []
        script = (
            "import sys\n"
            "for _ in range(6000):\n"
            "    sys.stderr.write('x' * 1000 + '\\n')\n"
            "sys.stderr.flush()\n"
            "print('finished', flush=True)\n"
        )
        result = run_streaming_process(
            [sys.executable, "-c", script],
            timeout=10,
            on_stdout_line=lines.append,
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(lines, ["finished"])
        self.assertLessEqual(len(result.stderr.encode("utf-8")), 66 * 1024)

    def test_timeout_is_measured_while_process_is_running(self):
        start = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            run_streaming_process(
                [sys.executable, "-c", "import time; time.sleep(10)"],
                timeout=0.3,
                on_stdout_line=lambda _line: None,
            )

        self.assertLess(time.monotonic() - start, 5)

    def test_captures_stderr_for_failed_process(self):
        result = run_streaming_process(
            [sys.executable, "-c", "import sys; print('failure', file=sys.stderr); sys.exit(7)"],
            timeout=5,
            on_stdout_line=lambda _line: None,
        )
        self.assertEqual(result.returncode, 7)
        self.assertIn("failure", result.stderr)


if __name__ == "__main__":
    unittest.main()
