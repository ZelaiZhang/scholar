"""Build and verify an installed wheel outside the source tree on any OS.

Run with the development environment: python scripts/verify_wheel.py
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path


def verify(repository: Path) -> None:
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    environment["PYTHONUTF8"] = "1"
    with tempfile.TemporaryDirectory(prefix="research-os-wheel-") as directory:
        root = Path(directory).resolve()

        def run(command: list[str]) -> None:
            subprocess.run(command, cwd=root, env=environment, check=True)

        run([
            sys.executable, "-m", "build", "--wheel",
            "--outdir", str(root / "dist"), str(repository),
        ])
        wheels = list((root / "dist").glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("expected exactly one newly built wheel")
        wheel = wheels[0]
        print(f"Wheel SHA256: {hashlib.sha256(wheel.read_bytes()).hexdigest()}", flush=True)
        installation = root / "venv"
        venv.EnvBuilder(with_pip=True).create(installation)
        python = installation / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        run([str(python), "-m", "pip", "install", str(wheel)])
        run([str(python), "-m", "pip", "check"])
        # Assert the editable source tree cannot accidentally satisfy the smoke.
        run([
            str(python), "-I", "-c",
            "import pathlib, research_os; "
            "p = pathlib.Path(research_os.__file__).resolve(); "
            f"assert not p.is_relative_to(pathlib.Path({str(repository)!r})), p",
        ])
        smoke = root / "installed_wheel_smoke.py"
        shutil.copy2(repository / "tests" / "installed_wheel_smoke.py", smoke)
        run([str(python), "-I", str(smoke), str(root / "workspace"), str(repository)])


if __name__ == "__main__":
    verify(Path(__file__).resolve().parents[1])
