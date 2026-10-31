"""Run pytest for hgs2-performance-lab and keep verifiable evidence in a new, unique directory.

Usage: python run_pytest_evidence.py <label> [pytest args...]

Writes <artifacts>/test-evidence/<UTC timestamp>-<label>/:
  command.txt, environment.json, git-head.txt, git-status-short.txt, git-diff-stat.txt,
  tree-manifest.sha256 (every working-tree file except .git/.venv/__pycache__/egg-info),
  junit.xml, console.txt (full pytest output), summary.json (counts parsed from junit.xml + console).
Never overwrites: aborts if the directory already exists. Writes nothing inside the repository.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"C:\Users\Ceng Zeki\Desktop\Projects\hgs2-performance-lab")
PYTHON = REPO / ".venv" / "Scripts" / "python.exe"
EVIDENCE_ROOT = Path(__file__).resolve().parents[1] / "test-evidence"
SKIP_DIRS = {".git", ".venv", "__pycache__", "hgs2_lab.egg-info", ".pytest_cache"}


def git(*args: str) -> str:
    return subprocess.run(["git", "--no-optional-locks", *args], cwd=REPO, capture_output=True, text=True,
                          check=True).stdout


def manifest() -> list[str]:
    lines = []
    for path in sorted(REPO.rglob("*")):
        rel = path.relative_to(REPO)
        if path.is_file() and not SKIP_DIRS.intersection(rel.parts):
            lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {rel.as_posix()}")
    return lines


def junit_counts(path: Path) -> dict:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    totals = {k: sum(int(s.get(k, 0)) for s in suites) for k in ("tests", "failures", "errors", "skipped")}
    totals["passed"] = totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"]
    failed = [f"{c.get('classname')}::{c.get('name')}" for c in root.iter("testcase")
              if c.find("failure") is not None or c.find("error") is not None]
    return {**totals, "failed_or_error_cases": failed}


def main() -> int:
    label, pytest_args = sys.argv[1], sys.argv[2:]
    started = datetime.now(timezone.utc)
    out = EVIDENCE_ROOT / f"{started.strftime('%Y%m%dT%H%M%SZ')}-{label}"
    out.mkdir(parents=True, exist_ok=False)
    junit = out / "junit.xml"
    cmd = [str(PYTHON), "-m", "pytest", "-p", "no:cacheprovider", "-rfEs", "--tb=long",
           f"--junitxml={junit}", *pytest_args]
    (out / "command.txt").write_text(subprocess.list2cmdline(cmd) + f"\n(cwd: {REPO})\n", encoding="utf-8")
    (out / "git-head.txt").write_text(git("rev-parse", "HEAD") + git("rev-parse", "--abbrev-ref", "HEAD"),
                                      encoding="utf-8")
    (out / "git-status-short.txt").write_text(git("status", "--short"), encoding="utf-8")
    (out / "git-diff-stat.txt").write_text(git("diff", "--stat"), encoding="utf-8")
    tree = manifest()
    (out / "tree-manifest.sha256").write_text("\n".join(tree) + "\n", encoding="utf-8")
    version = subprocess.run([str(PYTHON), "-c", "import sys,pytest,requests,urllib3; print(sys.version); "
                              "print('pytest', pytest.__version__, 'requests', requests.__version__, "
                              "'urllib3', urllib3.__version__)"], capture_output=True, text=True).stdout
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    with (out / "console.txt").open("w", encoding="utf-8", newline="\n") as console:
        proc = subprocess.Popen(cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                encoding="utf-8", errors="replace", env=env)
        assert proc.stdout is not None
        for line in proc.stdout:
            console.write(line)
            sys.stdout.write(line)
        code = proc.wait()
    finished = datetime.now(timezone.utc)
    last = [l for l in (out / "console.txt").read_text(encoding="utf-8").splitlines()
            if any(w in l for w in (" passed", " failed", " error", " deselected", "no tests ran"))]
    (out / "environment.json").write_text(json.dumps({
        "python_and_packages": version.strip().splitlines(), "platform": platform.platform(),
        "machine": platform.machine(), "python_executable": str(PYTHON)}, indent=2), encoding="utf-8")
    summary = {
        "label": label, "exit_code": code, "started_utc": started.isoformat(), "finished_utc": finished.isoformat(),
        "duration_s": round((finished - started).total_seconds(), 1),
        "git_head": git("rev-parse", "HEAD").strip(), "tree_files": len(tree),
        "tree_manifest_sha256": hashlib.sha256((out / "tree-manifest.sha256").read_bytes()).hexdigest(),
        "junit": junit_counts(junit) if junit.exists() else None,
        "console_summary_line": last[-1] if last else None,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nEVIDENCE_DIR={out}\nEXIT={code}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
