"""qaswarm.planning: deterministic template plan (phase 2).

The LLM-assisted planner (AG-01, slice 2c) is not part of this build. The template plan is the
deterministic fallback the design prescribes when no planner output is available.
"""

from qaswarm.planning.template import CRITICAL_TASK_TYPES, PlannedTask, build_template_plan

__all__ = ["CRITICAL_TASK_TYPES", "PlannedTask", "build_template_plan"]
