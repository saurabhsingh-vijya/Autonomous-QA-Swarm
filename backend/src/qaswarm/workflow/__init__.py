"""Workflow Engine core: enqueue, lease, heartbeat, complete/fail, reaper, backoff.

State machines live in ``qaswarm.domain.state_machines``; this package applies them to rows.
"""
