"""qaswarm.planning: deterministic planners.

- ``template``: the Execution Service plan (``env_prepare`` + one ``check`` task per engine) for
  a pinned repository (phase 2).
- ``planner``: the agent plan DAG (requirements → functional/API → evidence → report) with
  validation and a stable hash (phase 3).
- ``combined``: joins both into one job plan: repository checks run in the Execution Service,
  agents consume supplied inputs and the persisted check results.
"""

from qaswarm.planning.combined import build_job_plan
from qaswarm.planning.planner import PlanNode, build_plan, plan_hash, validate_plan
from qaswarm.planning.template import (
    CRITICAL_TASK_TYPES,
    PlannedTask,
    TemplatePlan,
    build_template_plan,
)

__all__ = [
    "CRITICAL_TASK_TYPES",
    "PlanNode",
    "PlannedTask",
    "TemplatePlan",
    "build_job_plan",
    "build_plan",
    "build_template_plan",
    "plan_hash",
    "validate_plan",
]
