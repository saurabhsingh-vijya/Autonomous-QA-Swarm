"""Run the API with uvicorn: ``python -m qaswarm.api.serve [--port 8000] [--host 127.0.0.1]``.

Equivalent to ``uvicorn qaswarm.api.app:create_app --factory`` with one Windows-specific
accommodation: some Windows App Control policies block the ``_multiprocessing`` extension of
uv-managed Pythons, and recent uvicorn versions import it eagerly (for ``--reload`` and
``--workers`` supervisors). This entry point runs a single process without those supervisors, so
when the extension cannot be loaded it installs an inert stand-in and continues. Reload and
multi-worker modes are intentionally not offered here; use plain ``uvicorn`` where it works.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import sys
import types


def _ensure_multiprocessing_importable() -> bool:
    try:
        importlib.import_module("_multiprocessing")
        return False
    except ImportError:
        import multiprocessing

        sys.modules.setdefault("_multiprocessing", types.ModuleType("_multiprocessing"))
        multiprocessing.allow_connection_pickling = lambda: None
        return True


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Autonomous QA Swarm API (single process)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args(argv)
    stubbed = _ensure_multiprocessing_importable()
    import uvicorn

    from qaswarm.api.app import create_app

    if stubbed:
        logging.getLogger("qaswarm.api.serve").warning(
            "_multiprocessing could not be imported (blocked by policy); running a single "
            "uvicorn process without reload/workers support"
        )
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":  # pragma: no cover - process entry point
    main()
