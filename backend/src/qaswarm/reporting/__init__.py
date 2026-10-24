"""qaswarm.reporting: basic JSON + HTML job report (phase 2).

The JSON report is the canonical source; HTML is rendered from it. PDF, SARIF and JUnit exports
and quality gates arrive in slices 1d/2d.
"""

from qaswarm.reporting.basic import build_report, compose_report, render_html

__all__ = ["build_report", "compose_report", "render_html"]
