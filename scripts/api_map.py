"""Print (or write) a map of every API endpoint:

    METHOD  /path   handler (routes file:line)  ->  Service.method (service file:line)

Run from the backend folder:
    python scripts/api_map.py                 # print to screen
    python scripts/api_map.py --markdown      # write docs/API_MAP.md
"""

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


@dataclass
class Endpoint:
    method: str
    path: str
    handler: str
    location: str
    service_calls: list[str] = field(default_factory=list)


def _service_methods() -> dict[str, str]:
    """'ClassName.method' -> 'relative/file.py:line' for every class method in the app."""
    found = {}
    for file in APP_DIR.rglob("*.py"):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        found[f"{node.name}.{item.name}"] = f"{file.relative_to(APP_DIR.parent)}:{item.lineno}"
    return found


def _router_prefix(tree: ast.Module) -> str:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "APIRouter":
            for keyword in node.keywords:
                if keyword.arg == "prefix" and isinstance(keyword.value, ast.Constant):
                    return keyword.value.value
    return ""


def _service_calls(function: ast.AST, known: dict[str, str]) -> list[str]:
    calls = []
    for node in ast.walk(function):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            name = f"{node.value.id}.{node.attr}"
            if name in known and name not in calls:
                calls.append(name)
    return calls


def collect_endpoints() -> list[Endpoint]:
    known = _service_methods()
    endpoints = []
    for file in sorted(APP_DIR.glob("*/routes.py")) + sorted(APP_DIR.glob("*/*_routes.py")):
        tree = ast.parse(file.read_text(encoding="utf-8"))
        prefix = _router_prefix(tree)
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if (
                    isinstance(decorator, ast.Call)
                    and isinstance(decorator.func, ast.Attribute)
                    and decorator.func.attr in HTTP_METHODS
                ):
                    sub_path = decorator.args[0].value if decorator.args else ""
                    endpoints.append(
                        Endpoint(
                            method=decorator.func.attr.upper(),
                            path=f"/api/v1{prefix}{sub_path}",
                            handler=node.name,
                            location=f"{file.relative_to(APP_DIR.parent)}:{node.lineno}",
                            service_calls=[f"{c} ({known[c]})" for c in _service_calls(node, known)],
                        )
                    )
    return endpoints


def render_markdown(endpoints: list[Endpoint]) -> str:
    lines = [
        "# API map",
        "",
        "Every endpoint, the handler that serves it, and the service method it calls.",
        "Regenerate with `python scripts/api_map.py --markdown`.",
        "",
    ]
    current_file = None
    for ep in endpoints:
        route_file = ep.location.split(":")[0]
        if route_file != current_file:
            current_file = route_file
            lines += ["", f"## {route_file}", "", "| Method | Path | Handler | Service method |", "|---|---|---|---|"]
        service = "<br>".join(ep.service_calls) or "-"
        lines.append(f"| {ep.method} | `{ep.path}` | `{ep.handler}` ({ep.location.split(':')[1]}) | {service} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    endpoints = collect_endpoints()
    if "--markdown" in sys.argv:
        target = APP_DIR.parent / "docs" / "API_MAP.md"
        target.parent.mkdir(exist_ok=True)
        target.write_text(render_markdown(endpoints), encoding="utf-8")
        print(f"Wrote {target} ({len(endpoints)} endpoints)")
        return
    for ep in endpoints:
        print(f"{ep.method:6} {ep.path:55} {ep.handler:32} -> {', '.join(ep.service_calls) or '-'}")


if __name__ == "__main__":
    main()
