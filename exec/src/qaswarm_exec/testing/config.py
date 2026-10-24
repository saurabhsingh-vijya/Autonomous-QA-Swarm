"""Test configuration model: environments, suites, scenarios, steps and assertions (phase 4).

Suites are declarative YAML/JSON documents. They come from the repository snapshot
(``.qaswarm/tests/*.yaml|yml|json`` or explicit paths) or inline from the job input. Loading
validates shape and enforces size bounds; it never evaluates anything. ``${name}`` placeholders are
substituted at run time from environment variables, suite/scenario test data and captured values.

Suite document (API)::

    kind: api
    name: items-api
    environment: default            # optional, see ``environments``
    data: {item_name: widget}       # test data, available as ${item_name}
    scenarios:
      - name: create and fetch
        steps:
          - name: health
            request: {method: GET, path: /health}
            expect:
              - status: 200
              - json_path: {path: "$.status", equals: ok}
              - response_time_ms: {lt: 2000}
          - name: create
            request: {method: POST, path: /api/items, json: {name: "${item_name}"}}
            expect: [{status: 201}]
            capture: {item_id: "$.id"}

Suite document (browser)::

    kind: browser
    name: home
    scenarios:
      - name: counter
        steps:
          - {name: open, goto: "/"}
          - {name: title, expect: {title_contains: "Sample Target"}}
          - {name: click, click: "#inc"}
          - {name: count, expect: {text: {selector: "#count", equals: "1"}}}
          - {name: shot, screenshot: after-click}
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SUITE_KINDS = frozenset({"api", "browser"})
HTTP_METHODS = frozenset({"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
API_ASSERTIONS = frozenset(
    {"status", "json_path", "header", "body_contains", "body_matches", "response_time_ms"}
)
BROWSER_ACTIONS = frozenset(
    {"goto", "click", "fill", "press", "wait_for", "expect", "screenshot", "check", "select"}
)
BROWSER_ASSERTIONS = frozenset(
    {"title_contains", "text", "visible", "hidden", "url_contains", "value", "count"}
)
MAX_FILE_BYTES = 256 * 1024
MAX_SUITES = 50
MAX_SCENARIOS = 200
MAX_STEPS = 1000
MAX_NAME = 200
DEFAULT_TIMEOUT_MS = 10_000
MAX_TIMEOUT_MS = 120_000
DISCOVERY_DIR = ".qaswarm/tests"
_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_.\-]*)\}")


class ConfigError(ValueError):
    """The test configuration is malformed; reported as a check ``error`` with the detail."""


@dataclass(frozen=True)
class Assertion:
    kind: str
    params: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> str:
        return f"{self.kind} {json.dumps(self.params, sort_keys=True, default=str)}"


@dataclass(frozen=True)
class Step:
    name: str
    action: str  # api: "request"; browser: one of BROWSER_ACTIONS
    params: dict[str, Any] = field(default_factory=dict)
    expect: tuple[Assertion, ...] = ()
    capture: dict[str, str] = field(default_factory=dict)
    timeout_ms: int = DEFAULT_TIMEOUT_MS


@dataclass(frozen=True)
class Scenario:
    name: str
    steps: tuple[Step, ...]
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Environment:
    name: str
    base_url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TestSuite:
    name: str
    kind: str
    scenarios: tuple[Scenario, ...]
    source: str
    environment: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    environments: dict[str, Environment] = field(default_factory=dict)

    @property
    def step_count(self) -> int:
        return sum(len(s.steps) for s in self.scenarios)


# ----------------------------------------------------------------------------- substitution
def substitute(value: Any, variables: dict[str, Any]) -> Any:
    """Replace ``${name}`` recursively. A whole-string placeholder keeps the variable's type."""
    if isinstance(value, str):
        whole = _PLACEHOLDER.fullmatch(value)
        if whole:
            return _lookup(whole.group(1), variables)

        def repl(m: re.Match[str]) -> str:
            found = _lookup(m.group(1), variables)
            return found if isinstance(found, str) else json.dumps(found)

        return _PLACEHOLDER.sub(repl, value)
    if isinstance(value, dict):
        return {k: substitute(v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [substitute(v, variables) for v in value]
    return value


def _lookup(name: str, variables: dict[str, Any]) -> Any:
    if name not in variables:
        raise ConfigError(f"undefined variable '${{{name}}}'")
    return variables[name]


# ------------------------------------------------------------------------------- validation
def _name(value: Any, what: str, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str) or not value.strip() or len(value) > MAX_NAME:
        raise ConfigError(f"{what}: name must be a non-empty string (≤ {MAX_NAME} chars)")
    return value.strip()


def _dict(value: Any, what: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{what}: expected a mapping")
    return dict(value)


def _timeout(value: Any, what: str) -> int:
    if value is None:
        return DEFAULT_TIMEOUT_MS
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ConfigError(f"{what}: timeout_ms must be a positive integer")
    return min(value, MAX_TIMEOUT_MS)


def _assertion(raw: Any, kind: str, what: str) -> Assertion:
    allowed = API_ASSERTIONS if kind == "api" else BROWSER_ASSERTIONS
    if not isinstance(raw, dict) or len(raw) != 1:
        raise ConfigError(f"{what}: each assertion is a single-key mapping, got {raw!r}")
    ((akind, params),) = raw.items()
    if akind not in allowed:
        raise ConfigError(f"{what}: unknown assertion '{akind}' for {kind} suites")
    if akind == "status":
        if isinstance(params, int) and not isinstance(params, bool):
            params = {"equals": params}
        elif isinstance(params, list) and all(isinstance(p, int) for p in params):
            params = {"in": params}
        elif not isinstance(params, dict):
            raise ConfigError(f"{what}: status expects an int, a list of ints or a mapping")
    elif akind in {"body_contains", "body_matches", "title_contains", "url_contains"}:
        if isinstance(params, str):
            params = {"value": params}
        elif not isinstance(params, dict) or "value" not in params:
            raise ConfigError(f"{what}: {akind} expects a string")
    elif akind in {"visible", "hidden"}:
        if isinstance(params, str):
            params = {"selector": params}
        elif not isinstance(params, dict) or "selector" not in params:
            raise ConfigError(f"{what}: {akind} expects a selector")
    elif akind == "response_time_ms":
        if isinstance(params, int) and not isinstance(params, bool):
            params = {"lt": params}
        elif not isinstance(params, dict) or "lt" not in params:
            raise ConfigError(f"{what}: response_time_ms expects an int or {{lt: int}}")
    elif not isinstance(params, dict):
        raise ConfigError(f"{what}: {akind} expects a mapping")
    if akind == "json_path" and not isinstance(params.get("path"), str):
        raise ConfigError(f"{what}: json_path needs a 'path'")
    if akind == "header" and not isinstance(params.get("name"), str):
        raise ConfigError(f"{what}: header needs a 'name'")
    if akind in {"text", "value", "count"} and not isinstance(params.get("selector"), str):
        raise ConfigError(f"{what}: {akind} needs a 'selector'")
    return Assertion(akind, dict(params))


def _api_step(raw: dict[str, Any], what: str) -> Step:
    request = _dict(raw.get("request"), f"{what}.request")
    if not request:
        raise ConfigError(f"{what}: api steps need a 'request' mapping")
    method = str(request.get("method", "GET")).upper()
    if method not in HTTP_METHODS:
        raise ConfigError(f"{what}: unsupported method '{method}'")
    path = request.get("path", request.get("url"))
    if not isinstance(path, str) or not path:
        raise ConfigError(f"{what}: request needs a 'path'")
    headers = _dict(request.get("headers"), f"{what}.request.headers")
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in headers.items()):
        raise ConfigError(f"{what}: request headers must be string → string")
    if "body" in request and "json" in request:
        raise ConfigError(f"{what}: request has both 'body' and 'json'")
    body = request.get("body")
    if body is not None and not isinstance(body, str):
        raise ConfigError(f"{what}: request body must be a string (use 'json' for objects)")
    params: dict[str, Any] = {
        "method": method,
        "path": path,
        "headers": headers,
        "body": body,
        "json": request.get("json"),
        "follow_redirects": bool(request.get("follow_redirects", True)),
    }
    return Step(
        name=_name(raw.get("name"), what, f"{method} {path}"),
        action="request",
        params=params,
        expect=tuple(_assertion(a, "api", what) for a in _list(raw.get("expect"), what)),
        capture=_capture(raw.get("capture"), what),
        timeout_ms=_timeout(raw.get("timeout_ms", request.get("timeout_ms")), what),
    )


def _browser_step(raw: dict[str, Any], what: str) -> Step:
    actions = [k for k in raw if k in BROWSER_ACTIONS]
    if len(actions) != 1:
        raise ConfigError(
            f"{what}: browser steps need exactly one action of {sorted(BROWSER_ACTIONS)}"
        )
    action = actions[0]
    value = raw[action]
    params: dict[str, Any]
    expect: tuple[Assertion, ...] = ()
    if action == "goto":
        if not isinstance(value, str):
            raise ConfigError(f"{what}: goto expects a path or URL")
        params = {"path": value}
    elif action in {"click", "wait_for", "check"}:
        if not isinstance(value, str):
            raise ConfigError(f"{what}: {action} expects a selector")
        params = {"selector": value}
    elif action in {"fill", "select"}:
        if not isinstance(value, dict) or "selector" not in value or "value" not in value:
            raise ConfigError(f"{what}: {action} expects {{selector, value}}")
        params = {"selector": str(value["selector"]), "value": value["value"]}
    elif action == "press":
        if not isinstance(value, dict) or "key" not in value:
            raise ConfigError(f"{what}: press expects {{selector?, key}}")
        params = {"selector": value.get("selector"), "key": str(value["key"])}
    elif action == "screenshot":
        params = {"label": str(value) if value else "screenshot"}
    else:  # expect
        raw_expect = value if isinstance(value, list) else [value]
        expect = tuple(_assertion(a, "browser", what) for a in raw_expect)
        params = {}
    expect += tuple(_assertion(a, "browser", what) for a in _list(raw.get("expect_also"), what))
    return Step(
        name=_name(raw.get("name"), what, action),
        action=action,
        params=params,
        expect=expect,
        timeout_ms=_timeout(raw.get("timeout_ms"), what),
    )


def _list(value: Any, what: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ConfigError(f"{what}: expected a list")
    return list(value)


def _capture(value: Any, what: str) -> dict[str, str]:
    out = _dict(value, f"{what}.capture")
    for k, v in out.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(k)) or not isinstance(v, str):
            raise ConfigError(f"{what}: capture entries are name → json path")
    return {str(k): v for k, v in out.items()}


def _environment(name: str, raw: Any) -> Environment:
    data = _dict(raw, f"environment '{name}'")
    base_url = data.get("base_url")
    if base_url is not None and not isinstance(base_url, str):
        raise ConfigError(f"environment '{name}': base_url must be a string")
    headers = _dict(data.get("headers"), f"environment '{name}'.headers")
    return Environment(
        name=name,
        base_url=base_url,
        headers={str(k): str(v) for k, v in headers.items()},
        variables=_dict(data.get("variables"), f"environment '{name}'.variables"),
    )


def load_suite(document: Any, source: str) -> TestSuite:
    doc = _dict(document, f"suite {source}")
    kind = str(doc.get("kind", "api")).lower()
    if kind not in SUITE_KINDS:
        raise ConfigError(f"suite {source}: kind must be one of {sorted(SUITE_KINDS)}")
    name = _name(doc.get("name"), f"suite {source}", Path(source).stem or "suite")
    scenarios: list[Scenario] = []
    total_steps = 0
    for si, raw_sc in enumerate(_list(doc.get("scenarios"), f"suite {name}")):
        sc = _dict(raw_sc, f"suite {name} scenario #{si}")
        sc_name = _name(sc.get("name"), f"suite {name} scenario #{si}", f"scenario-{si + 1}")
        steps: list[Step] = []
        for ti, raw_step in enumerate(_list(sc.get("steps"), f"{name}/{sc_name}")):
            what = f"{name}/{sc_name}/step #{ti + 1}"
            step_doc = _dict(raw_step, what)
            steps.append(
                _api_step(step_doc, what) if kind == "api" else _browser_step(step_doc, what)
            )
        if not steps:
            raise ConfigError(f"{name}/{sc_name}: scenario has no steps")
        total_steps += len(steps)
        scenarios.append(
            Scenario(sc_name, tuple(steps), _dict(sc.get("data"), f"{name}/{sc_name}.data"))
        )
    if not scenarios:
        raise ConfigError(f"suite {name}: no scenarios")
    if len(scenarios) > MAX_SCENARIOS or total_steps > MAX_STEPS:
        raise ConfigError(f"suite {name}: too many scenarios/steps")
    envs = {
        str(k): _environment(str(k), v)
        for k, v in _dict(doc.get("environments"), f"suite {name}.environments").items()
    }
    environment = doc.get("environment")
    if environment is not None and not isinstance(environment, str):
        raise ConfigError(f"suite {name}: environment must be a name")
    return TestSuite(
        name=name,
        kind=kind,
        scenarios=tuple(scenarios),
        source=source,
        environment=environment,
        data=_dict(doc.get("data"), f"suite {name}.data"),
        environments=envs,
    )


def parse_document(text: str, source: str) -> Any:
    if len(text.encode("utf-8", errors="replace")) > MAX_FILE_BYTES:
        raise ConfigError(f"{source}: file exceeds {MAX_FILE_BYTES} bytes")
    try:
        if source.endswith(".json"):
            return json.loads(text)
        return yaml.safe_load(text)
    except (yaml.YAMLError, json.JSONDecodeError) as exc:
        raise ConfigError(f"{source}: cannot parse: {str(exc)[:200]}") from exc


def discover_suites(
    workspace: Path, *, kind: str, paths: list[str] | None = None
) -> list[TestSuite]:
    """Load suites of ``kind`` from explicit relative ``paths`` or from ``.qaswarm/tests``."""
    root = workspace.resolve()
    candidates: list[Path] = []
    if paths:
        for p in paths:
            candidate = (root / p).resolve()
            if not str(candidate).startswith(str(root)) or ".." in Path(p).parts:
                raise ConfigError(f"suite path escapes the snapshot: {p}")
            if candidate.is_dir():
                candidates.extend(
                    sorted(candidate.glob("*.y*ml")) + sorted(candidate.glob("*.json"))
                )
            elif candidate.is_file():
                candidates.append(candidate)
            else:
                raise ConfigError(f"suite path not found in the snapshot: {p}")
    else:
        base = root / DISCOVERY_DIR
        if base.is_dir():
            candidates = sorted(
                p for p in base.rglob("*") if p.is_file() and p.suffix in {".yaml", ".yml", ".json"}
            )
    suites: list[TestSuite] = []
    for path in candidates:
        rel = path.relative_to(root).as_posix()
        doc = parse_document(path.read_text(encoding="utf-8", errors="replace"), rel)
        if isinstance(doc, dict) and str(doc.get("kind", "api")).lower() != kind:
            continue
        suites.append(load_suite(doc, rel))
        if len(suites) > MAX_SUITES:
            raise ConfigError(f"more than {MAX_SUITES} suites")
    return suites


def load_inline(documents: list[Any], *, kind: str) -> list[TestSuite]:
    suites = []
    for i, doc in enumerate(documents[:MAX_SUITES]):
        suite = load_suite(doc, f"inline#{i + 1}")
        if suite.kind != kind:
            raise ConfigError(f"inline suite '{suite.name}' is kind {suite.kind}, expected {kind}")
        suites.append(suite)
    return suites


def load_environments(raw: Any) -> dict[str, Environment]:
    return {str(k): _environment(str(k), v) for k, v in _dict(raw, "environments").items()}
