#!/usr/bin/env python3
"""Run llama-server and sanitize known noisy/buggy log patterns."""

from __future__ import annotations

import re
import subprocess
import sys

_TS_SPLIT_RE = re.compile(r"(?=\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3} \| )")
_UNACCOUNTED_RE = re.compile(r"(\+\s+)(\d{10,})(\s*\|?)")
_N_CTX_WARNING_FRAGMENT = "n_ctx_seq ("
_N_CTX_WARNING_SUFFIX = "< n_ctx_train"


def _split_glued_timestamps(line: str) -> list[str]:
    line = line.rstrip("\n")
    if not line:
        return [line]
    parts = [part for part in _TS_SPLIT_RE.split(line) if part]
    return parts or [line]


def _sanitize_unaccounted(line: str) -> str:
    if "common_memory_breakdown_print:" not in line or "CUDA" not in line:
        return line

    def _replace(match: re.Match[str]) -> str:
        value = int(match.group(2))
        if value < 10_000_000:
            return match.group(0)
        return f"{match.group(1)}0{match.group(3)}"

    return _UNACCOUNTED_RE.sub(_replace, line)


def _emit_sanitized(line: str, last_line: str | None) -> str:
    for piece in _split_glued_timestamps(line):
        if (
            _N_CTX_WARNING_FRAGMENT in piece
            and _N_CTX_WARNING_SUFFIX in piece
            and "the full capacity of the model will not be utilized" in piece
        ):
            continue
        sanitized = _sanitize_unaccounted(piece)
        if sanitized == last_line:
            continue
        sys.stdout.write(sanitized + "\n")
        sys.stdout.flush()
        last_line = sanitized
    return last_line or ""


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: llm_log_sanitizer.py <binary> [args...]", file=sys.stderr)
        return 64

    proc = subprocess.Popen(
        sys.argv[1:],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    last_line: str | None = None
    assert proc.stdout is not None
    for raw in proc.stdout:
        last_line = _emit_sanitized(raw, last_line)

    return proc.wait()


if __name__ == "__main__":
    raise SystemExit(main())
