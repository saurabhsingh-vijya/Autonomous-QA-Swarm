"""A deliberately small JSON-path subset for assertions and captures.

Grammar: ``$`` root, ``.name`` member, ``[n]`` index (negative allowed), ``[*]`` all items
(returns a list), ``.length()`` on lists/strings/objects. Bracketed quoted keys ``['a b']`` are
accepted for names with spaces. Anything else raises ``JsonPathError``. No eval, no filters.
"""

from __future__ import annotations

import re
from typing import Any

_TOKEN = re.compile(
    r"""\.length\(\)|\.([A-Za-z_][A-Za-z0-9_\-]*)|\[(\-?\d+)\]|\[\*\]|\['([^']*)'\]|\["([^"]*)"\]"""
)


class JsonPathError(ValueError):
    pass


class _Missing:
    def __repr__(self) -> str:
        return "<missing>"


MISSING = _Missing()


def _step(value: Any, name: str | None, index: int | None, star: bool, length: bool) -> Any:
    if isinstance(value, list) and star:
        return list(value)
    if length:
        if isinstance(value, list | str | dict):
            return len(value)
        return MISSING
    if name is not None:
        if isinstance(value, dict):
            return value.get(name, MISSING)
        return MISSING
    if index is not None:
        if isinstance(value, list) and -len(value) <= index < len(value):
            return value[index]
        return MISSING
    return MISSING


def resolve(document: Any, path: str) -> Any:
    """Return the value at ``path`` or :data:`MISSING`. ``[*]`` fans out to a list."""
    if not path.startswith("$"):
        raise JsonPathError(f"path must start with '$': {path!r}")
    pos = 1
    values: list[Any] = [document]
    fanned = False
    while pos < len(path):
        m = _TOKEN.match(path, pos)
        if not m:
            raise JsonPathError(f"unsupported json path segment at {pos}: {path[pos:]!r}")
        pos = m.end()
        text = m.group(0)
        name = m.group(1) or m.group(3) or m.group(4)
        index = int(m.group(2)) if m.group(2) is not None else None
        star = text == "[*]"
        length = text == ".length()"
        if star:
            out: list[Any] = []
            for v in values:
                if isinstance(v, list):
                    out.extend(v)
            values, fanned = out, True
            continue
        values = [_step(v, name, index, False, length) for v in values]
    if fanned:
        return [v for v in values if v is not MISSING]
    return values[0]
