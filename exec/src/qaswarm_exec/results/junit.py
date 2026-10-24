"""JUnit XML (xunit2) → design test statuses. Parsed defensively; the file is untrusted output."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from qaswarm_exec.tools.base import TestResult

MAX_BYTES = 50 * 1024 * 1024
MAX_MESSAGE = 4000


def _message(el: ET.Element) -> str:
    msg = el.get("message") or ""
    body = (el.text or "").strip()
    text = msg if msg else body
    if msg and body and body not in msg:
        text = f"{msg}\n{body}"
    return text[:MAX_MESSAGE]


def parse_junit(path: Path) -> list[TestResult]:
    data = path.read_bytes()
    if len(data) > MAX_BYTES or b"<!DOCTYPE" in data or b"<!ENTITY" in data:
        raise ValueError("junit xml rejected: too large or contains DTD/entities")
    root = ET.fromstring(data)  # noqa: S314 - DTD/entities rejected above
    out: list[TestResult] = []
    for case in root.iter("testcase"):
        classname = case.get("classname") or ""
        name = case.get("name") or "?"
        file = case.get("file")
        node = f"{classname}::{name}" if classname else name
        try:
            duration_ms = int(float(case.get("time") or 0) * 1000)
        except ValueError:
            duration_ms = 0
        status, message = "passed", None
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        if failure is not None:
            status, message = "failed", _message(failure)
        elif error is not None:
            # Setup/teardown errors are recorded as failed with a note, never silently excluded.
            status, message = "failed", "error (setup/teardown or collection): " + _message(error)
        elif skipped is not None:
            status, message = "skipped", _message(skipped) or "skipped"
        out.append(
            TestResult(
                node_id=node,
                name=name,
                status=status,
                duration_ms=duration_ms,
                file=file,
                message=message,
            )
        )
    return out
