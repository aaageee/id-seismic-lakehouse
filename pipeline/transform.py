"""Silver/gold layer: run the dbt project and surface its results."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import config


class DbtNotFound(RuntimeError):
    pass


def _dbt_binary() -> str:
    override = os.environ.get("SEISMIC_DBT_BIN")
    if override:
        return override
    found = shutil.which("dbt")
    if found:
        return found
    candidate = Path(sys.executable).with_name("dbt")
    if candidate.exists():
        return str(candidate)
    raise DbtNotFound(
        "dbt executable not found. Install dependencies first: "
        "`pip install -r requirements.txt` (or `uv sync`) and activate the environment."
    )


def run_dbt(
    command: str = "build",
    *,
    select: str | None = None,
    full_refresh: bool = False,
    quiet: bool = False,
    db_path: Path | None = None,
    extra_args: list[str] | None = None,
) -> None:
    """Invoke dbt in the repo root with the warehouse path injected."""
    args = [
        _dbt_binary(),
        command,
        "--profiles-dir",
        str(config.ROOT),
        "--project-dir",
        str(config.ROOT),
    ]
    if select:
        args += ["--select", select]
    if full_refresh:
        args.append("--full-refresh")
    if quiet:
        args.append("--quiet")
    if extra_args:
        args += extra_args

    env = os.environ.copy()
    env["SEISMIC_DB"] = str(db_path or config.db_path())
    env.setdefault("DBT_SEND_ANONYMOUS_USAGE_STATS", "false")
    print(f"[dbt] {' '.join(args[1:])}")
    subprocess.run(args, cwd=config.ROOT, env=env, check=True)


def run_pipeline(
    *,
    full_refresh: bool = False,
    select: str | None = None,
    db_path: Path | None = None,
) -> None:
    run_dbt("build", select=select, full_refresh=full_refresh, db_path=db_path)
