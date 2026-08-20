#!/usr/bin/env python3
"""Run a subprocess with live stdout streaming and a real wall-clock timeout."""

from __future__ import annotations

import os
import queue
import signal
import subprocess
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence


STDERR_LIMIT = 64 * 1024


@dataclass(frozen=True)
class ProcessResult:
    """Result returned after a streamed process exits."""

    returncode: int
    stderr: str


def _terminate_process_tree(proc: subprocess.Popen[str]) -> None:
    """Terminate the child and, where supported, its process group."""
    if proc.poll() is not None:
        return

    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return

    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=2)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def run_streaming_process(
    cmd: Sequence[str],
    *,
    timeout: float,
    on_stdout_line: Callable[[str], None],
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> ProcessResult:
    """Run ``cmd`` while draining both pipes and enforcing ``timeout``.

    ``on_stdout_line`` is called for every complete stdout line without its
    trailing newline. The last 64 KiB of stderr is retained for diagnostics.
    """
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    popen_kwargs: dict[str, object] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "bufsize": 1,
        "cwd": cwd,
        "env": env,
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(list(cmd), **popen_kwargs)
    assert proc.stdout is not None
    assert proc.stderr is not None

    events: queue.Queue[tuple[str, str | None]] = queue.Queue()

    def drain(name: str, stream) -> None:
        try:
            for line in iter(stream.readline, ""):
                events.put((name, line))
        finally:
            stream.close()
            events.put((name, None))

    readers = [
        threading.Thread(target=drain, args=("stdout", proc.stdout), daemon=True),
        threading.Thread(target=drain, args=("stderr", proc.stderr), daemon=True),
    ]
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + timeout
    finished_streams = 0
    stderr_chunks: deque[str] = deque()
    stderr_size = 0

    try:
        while finished_streams < 2:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise subprocess.TimeoutExpired(cmd, timeout)

            try:
                stream_name, line = events.get(timeout=min(0.1, remaining))
            except queue.Empty:
                continue

            if line is None:
                finished_streams += 1
                continue

            if stream_name == "stdout":
                on_stdout_line(line.rstrip("\r\n"))
                continue

            stderr_chunks.append(line)
            stderr_size += len(line.encode("utf-8", errors="replace"))
            while stderr_size > STDERR_LIMIT and len(stderr_chunks) > 1:
                removed = stderr_chunks.popleft()
                stderr_size -= len(removed.encode("utf-8", errors="replace"))

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(cmd, timeout)
        returncode = proc.wait(timeout=remaining)
    except BaseException as exc:
        _terminate_process_tree(proc)
        for reader in readers:
            reader.join(timeout=1)
        if isinstance(exc, subprocess.TimeoutExpired):
            exc.stderr = "".join(stderr_chunks)
        raise
    finally:
        if proc.poll() is None:
            _terminate_process_tree(proc)

    for reader in readers:
        reader.join(timeout=1)
    return ProcessResult(returncode=returncode, stderr="".join(stderr_chunks))
