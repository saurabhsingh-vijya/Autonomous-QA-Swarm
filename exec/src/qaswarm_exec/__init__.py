"""qaswarm_exec — Execution Service host agent (phase 2).

Leases tasks from the control plane's narrow internal API, fetches the pinned snapshot into a
disposable workspace, runs check engines through a process runtime, uploads evidence and reports
a schema-shaped worker result. It never connects to the control-plane database and imports
nothing from ``qaswarm``.
"""

__version__ = "0.1.0"
