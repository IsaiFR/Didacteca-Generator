"""Comprueba una instalación limpia y el contrato HTTP sin servicios reales."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path
from typing import Any


_SOURCE_ITEMS = ("src", "tests", "pytest.ini", "requirements.txt", ".env.example")
_PYTEST_SUMMARY = re.compile(
    r"^\d+ (?:passed|failed|error|errors|skipped|xfailed|xpassed|warning|warnings)"
    r"(?:, \d+ (?:passed|failed|error|errors|skipped|xfailed|xpassed|warning|warnings))*"
    r" in \d+(?:\.\d+)?s$"
)
_API_SMOKE = r'''
import sys
sys.path.insert(0, "src")
from fastapi.testclient import TestClient
from didacteca_ai.main import create_app

class NeverExecute:
    calls = 0
    async def execute(self, request):
        self.calls += 1
        raise AssertionError("La prevalidación debe rechazar antes de ejecutar.")

service = NeverExecute()
app = create_app(service=service)
with TestClient(app) as client:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    operation = response.json()["paths"]["/execute"]["post"]
    schema_ref = operation["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    schema_name = schema_ref.rsplit("/", 1)[-1]
    request_schema = response.json()["components"]["schemas"][schema_name]
    assert set(request_schema["properties"]) == {"action", "book_id", "section_id", "instructions"}

    rejected = client.post(
        "/execute",
        json={"action": "chat", "section_id": "section_01", "instructions": "Explica el tema."},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "MISSING_INPUT_FIELDS"
    assert rejected.json()["error"]["details"]["missing_fields"] == ["book_id"]
    assert service.calls == 0
'''


class CheckFailure(Exception):
    def __init__(self, step: str, returncode: int) -> None:
        self.step = step
        self.returncode = returncode
        super().__init__(step)


def _clean_subprocess_env() -> dict[str, str]:
    env = os.environ.copy()
    for name in tuple(env):
        upper = name.upper()
        if (
            upper.startswith(("OPENAI_", "PROVIDED_SERVICE_", "DIDACTECA_", "PIP_"))
            or upper in {"PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"}
        ):
            env.pop(name, None)
    return env


def _run_step(
    report: dict[str, Any],
    name: str,
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    timeout: int = 900,
) -> str:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        report["steps"].append({"name": name, "status": "failed", "reason": "timeout"})
        raise CheckFailure(name, 124) from None
    except OSError as error:
        report["steps"].append(
            {"name": name, "status": "failed", "reason": type(error).__name__}
        )
        raise CheckFailure(name, 1) from None

    step: dict[str, Any] = {
        "name": name,
        "status": "passed" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
    }
    if name == "pip_check":
        step["summary"] = (
            "No broken requirements found."
            if completed.returncode == 0
            else "Dependency inconsistencies found."
        )
    elif name == "pytest":
        output = completed.stdout + "\n" + completed.stderr
        step["summary"] = next(
            (line.strip() for line in reversed(output.splitlines()) if _PYTEST_SUMMARY.fullmatch(line.strip())),
            "Pytest summary unavailable.",
        )
    report["steps"].append(step)
    if completed.returncode:
        raise CheckFailure(name, completed.returncode)
    return completed.stdout.strip()


def _copy_clean_sources(source: Path, destination: Path) -> None:
    ignored = shutil.ignore_patterns("__pycache__", "*.py[cod]", ".pytest_cache")
    for name in _SOURCE_ITEMS:
        item = source / name
        if item.is_dir():
            shutil.copytree(item, destination / name, ignore=ignored)
        elif item.is_file():
            shutil.copy2(item, destination / name)
        else:
            raise FileNotFoundError(name)


def _default_report_path(root: Path) -> Path:
    platform_name = "windows" if os.name == "nt" else platform.system().lower()
    return root / "output" / f"install-check-{platform_name}.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--report",
        type=Path,
        help="Ruta de salida JSON (predeterminado: output/install-check-<sistema>.json).",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    report_path = args.report or _default_report_path(root)
    if not report_path.is_absolute():
        report_path = root / report_path
    report: dict[str, Any] = {
        "status": "running",
        "runtime": {
            "os": platform.system(),
            "python": platform.python_version(),
        },
        "steps": [],
    }
    exit_code = 0
    child_env = _clean_subprocess_env()

    try:
        with tempfile.TemporaryDirectory(prefix="didacteca-install-check-") as temporary:
            temporary_root = Path(temporary)
            clean_root = temporary_root / "project"
            clean_root.mkdir()
            try:
                _copy_clean_sources(root, clean_root)
            except Exception as error:
                report["steps"].append(
                    {"name": "copy_sources", "status": "failed", "reason": type(error).__name__}
                )
                raise CheckFailure("copy_sources", 1) from None
            report["steps"].append({"name": "copy_sources", "status": "passed"})

            environment_path = temporary_root / "venv"
            try:
                venv.EnvBuilder(with_pip=True).create(environment_path)
            except Exception as error:
                report["steps"].append(
                    {"name": "create_venv", "status": "failed", "reason": type(error).__name__}
                )
                raise CheckFailure("create_venv", 1) from None
            report["steps"].append({"name": "create_venv", "status": "passed"})

            python = (
                environment_path / "Scripts" / "python.exe"
                if os.name == "nt"
                else environment_path / "bin" / "python"
            )
            report["runtime"]["isolated_python"] = _run_step(
                report,
                "isolated_python",
                [str(python), "-c", "import platform; print(platform.python_version())"],
                cwd=clean_root,
                env=child_env,
                timeout=30,
            )
            _run_step(
                report,
                "install_requirements",
                [
                    str(python),
                    "-m",
                    "pip",
                    "--isolated",
                    "install",
                    "--disable-pip-version-check",
                    "--no-input",
                    "-r",
                    "requirements.txt",
                ],
                cwd=clean_root,
                env=child_env,
            )
            _run_step(
                report,
                "pip_check",
                [str(python), "-m", "pip", "--isolated", "check"],
                cwd=clean_root,
                env=child_env,
                timeout=120,
            )
            _run_step(
                report,
                "pytest",
                [str(python), "-m", "pytest", "-q"],
                cwd=clean_root,
                env=child_env,
                timeout=600,
            )
            _run_step(
                report,
                "api_contract_smoke",
                [str(python), "-c", _API_SMOKE],
                cwd=clean_root,
                env=child_env,
                timeout=60,
            )
    except CheckFailure as error:
        report["status"] = "failed"
        report["failed_step"] = error.step
        exit_code = error.returncode
    except Exception as error:
        report["status"] = "failed"
        report["failed_step"] = "harness"
        report["failure_type"] = type(error).__name__
        exit_code = 1
    else:
        report["status"] = "passed"

    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as error:
        print(f"No se pudo escribir el reporte ({type(error).__name__}).", file=sys.stderr)
        return exit_code or 1

    print(
        f"Sistema: {report['runtime']['os']}; Python base: {report['runtime']['python']}; "
        f"Python aislado: {report['runtime'].get('isolated_python', 'no creado')}"
    )
    for step in report["steps"]:
        summary = f" — {step['summary']}" if "summary" in step else ""
        print(f"{step['name']}: {step['status']}{summary}")

    if exit_code:
        print(f"Instalación limpia falló en {report.get('failed_step')}; revisa el reporte JSON.")
    else:
        print(f"Instalación limpia verificada; reporte JSON: {report_path}")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
