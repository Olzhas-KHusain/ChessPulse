"""Validate the observability configuration without Docker.

Checks (all offline):

* every YAML/JSON file under observability/ parses;
* every metric referenced by Prometheus alert rules and the Grafana dashboard
  is one the backend actually emits (see backend/app/observability/metrics.py);
* every PromQL label is in the bounded label set;
* every alert has severity, summary, description and a runbook annotation that
  points at an existing heading in docs/observability.md;
* the dashboard uses a provisioned datasource uid and has panels;
* the compose stacks reference the expected services.

Run from the repository root:

    python scripts/check-observability-config.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
OBS = ROOT / "observability"
DOC = ROOT / "docs" / "observability.md"

# Instruments in backend/app/observability/metrics.py after OTel -> Prometheus
# translation (dots -> underscores, counters get _total, unit `s` -> _seconds).
METRICS = {
    "chesspulse_http_server_requests_total",
    "chesspulse_http_server_duration_seconds_bucket",
    "chesspulse_http_server_duration_seconds_count",
    "chesspulse_http_server_duration_seconds_sum",
    "chesspulse_provider_requests_total",
    "chesspulse_provider_duration_seconds_bucket",
    "chesspulse_provider_duration_seconds_count",
    "chesspulse_provider_duration_seconds_sum",
    "chesspulse_cache_refreshes_total",
    "chesspulse_cache_refresh_duration_seconds_bucket",
    "chesspulse_cache_refresh_duration_seconds_count",
    "chesspulse_cache_refresh_duration_seconds_sum",
    "chesspulse_analysis_jobs_total",
    "chesspulse_analysis_job_duration_seconds_bucket",
    "chesspulse_analysis_job_duration_seconds_count",
    "chesspulse_analysis_job_duration_seconds_sum",
    "chesspulse_ingestion_games_total",
    "chesspulse_board_operations_total",
    "chesspulse_board_operation_duration_seconds_bucket",
    "chesspulse_board_operation_duration_seconds_count",
    "chesspulse_board_operation_duration_seconds_sum",
}

LABELS = {
    "http_request_method",
    "http_route",
    "http_response_status_code",
    "chesspulse_provider_resource",
    "chesspulse_provider_outcome",
    "chesspulse_cache_outcome",
    "chesspulse_analysis_outcome",
    "chesspulse_ingestion_complete",
    "chesspulse_board_operation",
    "chesspulse_board_outcome",
    # Prometheus built-ins used by platform selectors and histograms.
    "job",
    "instance",
    "le",
}

_METRIC_TOKEN = re.compile(r"\bchesspulse_[a-z0-9_]+\b")
_LABEL_TOKEN = re.compile(r"\{([^}]*)\}")
_LABEL_NAME = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=~|!~|!=|=)")
_GROUP_TOKEN = re.compile(r"(?:by|without|on|ignoring)\s*\(([^)]*)\)")
PROBLEMS: list[str] = []


def problem(message: str) -> None:
    PROBLEMS.append(message)


def load_yaml(path: Path) -> object:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError, OSError) as exc:
        problem(f"{path.relative_to(ROOT)}: not valid YAML ({type(exc).__name__}: {exc})")
        return None


def load_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        problem(f"{path.relative_to(ROOT)}: not valid JSON ({type(exc).__name__}: {exc})")
        return None


def slug(heading: str) -> str:
    text = heading.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text).strip("-")


def check_expressions(where: str, expression: str) -> None:
    # Label selectors start with `chesspulse_` too; remove them before looking
    # for metric names so `chesspulse_provider_outcome` is not mistaken for one.
    for block in _LABEL_TOKEN.findall(expression):
        for label in _LABEL_NAME.findall(block):
            if label not in LABELS:
                problem(f"{where}: unknown label `{label}`")
    for group in _GROUP_TOKEN.findall(expression):
        for label in (item.strip() for item in group.split(",")):
            if label and label != "__name__" and label not in LABELS:
                problem(f"{where}: unknown grouping label `{label}`")
    without_labels = _LABEL_TOKEN.sub("", _GROUP_TOKEN.sub("", expression))
    for metric in _METRIC_TOKEN.findall(without_labels):
        if metric not in METRICS:
            problem(f"{where}: unknown metric `{metric}`")


def check_alerts() -> None:
    path = OBS / "prometheus" / "alerts.yml"
    data = load_yaml(path)
    if not isinstance(data, dict):
        return
    if not DOC.is_file():
        problem("docs/observability.md is missing (alert runbooks point at it)")
        anchors: set[str] = set()
    else:
        anchors = {
            slug(line.lstrip("#"))
            for line in DOC.read_text(encoding="utf-8").splitlines()
            if line.startswith("#")
        }

    names: set[str] = set()
    for group in data.get("groups", []):
        for rule in group.get("rules", []):
            name = rule.get("alert", "<unnamed>")
            if name in names:
                problem(f"duplicate alert name `{name}`")
            names.add(name)
            annotations = rule.get("annotations", {})
            labels = rule.get("labels", {})
            for field in ("severity",):
                if not labels.get(field):
                    problem(f"{name}: missing labels.{field}")
            for field in ("summary", "description", "runbook"):
                if not annotations.get(field):
                    problem(f"{name}: missing annotations.{field}")
            runbook = annotations.get("runbook", "")
            if not runbook.startswith("docs/"):
                problem(f"{name}: runbook must point inside docs/, got `{runbook}`")
            elif "#" in runbook:
                anchor = runbook.split("#", 1)[1]
                if anchors and anchor not in anchors:
                    problem(f"{name}: runbook anchor `#{anchor}` not found in docs/observability.md")
            check_expressions(f"alerts.yml/{name}", rule.get("expr", ""))
    if not names:
        problem("alerts.yml: no alert rules found")


def check_dashboard() -> None:
    path = OBS / "grafana" / "dashboards" / "chesspulse-overview.json"
    data = load_json(path)
    if not isinstance(data, dict):
        return
    panels = data.get("panels", [])
    if len(panels) < 5:
        problem("dashboard: expected at least 5 panels")
    for panel in panels:
        title = panel.get("title", "<untitled>")
        datasource = panel.get("datasource", {})
        if datasource.get("uid") != "prometheus":
            problem(f"dashboard/{title}: datasource uid must be `prometheus`")
        for target in panel.get("targets", []):
            check_expressions(f"dashboard/{title}", target.get("expr", ""))


def check_datasources() -> None:
    path = OBS / "grafana" / "provisioning" / "datasources" / "datasources.yaml"
    data = load_yaml(path)
    if not isinstance(data, dict):
        return
    uids = {item.get("uid") for item in data.get("datasources", [])}
    for expected in ("prometheus", "tempo", "loki"):
        if expected not in uids:
            problem(f"datasources.yaml: missing `{expected}`")


def check_compose() -> None:
    main = load_yaml(ROOT / "docker-compose.yml")
    if isinstance(main, dict):
        services = main.get("services", {})
        for name in ("db", "app", "worker"):
            if name not in services:
                problem(f"docker-compose.yml: missing service `{name}`")
        for name in ("app", "worker"):
            env = services.get(name, {}).get("environment", {})
            if "OTEL_ENABLED" not in env:
                problem(f"docker-compose.yml/{name}: OTEL_ENABLED is not wired")

    obs = load_yaml(OBS / "docker-compose.observability.yml")
    if isinstance(obs, dict):
        services = obs.get("services", {})
        for name in (
            "otel-collector",
            "prometheus",
            "alertmanager",
            "tempo",
            "loki",
            "grafana",
            "oncall",
        ):
            if name not in services:
                problem(f"observability compose: missing service `{name}`")


def check_alertmanager() -> None:
    data = load_yaml(OBS / "alertmanager" / "alertmanager.yml")
    if not isinstance(data, dict):
        return
    receivers = data.get("receivers", [])
    urls = [config.get("url", "") for receiver in receivers for config in receiver.get("webhook_configs", [])]
    if not any(url.endswith(":8080/alerts") for url in urls):
        problem("alertmanager.yml: no webhook pointing at the on-call service (:8080/alerts)")
    if "credentials_file" not in json.dumps(data):
        problem("alertmanager.yml: the on-call webhook must use a credentials_file token")


def check_collector() -> None:
    data = load_yaml(OBS / "otel-collector" / "config.yaml")
    if not isinstance(data, dict):
        return
    pipelines = data.get("service", {}).get("pipelines", {})
    for signal in ("traces", "metrics", "logs"):
        if signal not in pipelines:
            problem(f"otel-collector: missing `{signal}` pipeline")


def main() -> int:
    for path in sorted(OBS.rglob("*.yaml")):
        load_yaml(path)
    for path in sorted(OBS.rglob("*.yml")):
        load_yaml(path)
    for path in sorted(OBS.rglob("*.json")):
        load_json(path)

    check_alerts()
    check_dashboard()
    check_datasources()
    check_compose()
    check_alertmanager()
    check_collector()

    if PROBLEMS:
        print(f"observability config: {len(PROBLEMS)} problem(s)")
        for item in PROBLEMS:
            print(f"  - {item}")
        return 1
    print("observability config: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
