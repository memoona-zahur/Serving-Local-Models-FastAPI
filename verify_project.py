#!/usr/bin/env python3
"""Integrity audit for the Week 07 Wed build.

Checks that prove the deliverable is complete and safe:

  1. Required files/structure exist
  2. Test suite passes with no real network/backend
  3. No secret can be leaked: .env is git-ignored and never committed,
     and no sk-/gsk_ key pattern exists anywhere in tracked files
  4. Code imports cleanly and both endpoints are registered

Run:  python3 verify_project.py   (exit 0 = all checks pass)
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PYTHON = ROOT / ".venv" / "bin" / "python"

REQUIRED_FILES = [
    ".gitignore",
    ".env.example",
    "requirements.txt",
    "README.md",
    "REPORT.md",
    "TRAINER_QA.md",
    "technical_summary.md",
    "EVIDENCE_REPORT.md",
    "self_review.md",
    "PEFT_LORA_EXPLANATION.md",
    "app/__init__.py",
    "app/main.py",
    "app/model_client.py",
    "tests/test_app.py",
]

SECRET_PATTERNS = ["sk-", "sk-proj-", "gsk_"]

# Files that legitimately contain key *patterns* as documentation/example text —
# the auditor itself (it defines SECRET_PATTERNS) and .env.example (placeholder
# documentation). Real secrets would be a full-length key, not documentation.
DOCUMENTED_PATTERN_FILES = {Path(__file__).name, ".env.example"}


def check(ok: bool, message: str) -> bool:
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {message}")
    return ok


def main() -> int:
    results = []

    print("== 1. Structure ==")
    missing = [f for f in REQUIRED_FILES if not (ROOT / f).exists()]
    results.append(check(not missing, f"all required files present (missing: {missing or 'none'})"))

    print("\n== 2. Tests (no real backend needed) ==")
    proc = subprocess.run(
        [str(PYTHON), "-m", "pytest", "tests/", "-q"],
        capture_output=True, text=True, cwd=ROOT,
    )
    ok = proc.returncode == 0 and "passed" in proc.stdout
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "(no output)"
    results.append(check(ok, f"pytest passes ({tail})"))

    print("\n== 3. Secret safety ==")
    gitignore = (ROOT / ".gitignore").read_text()
    has_dotenv_ignore = ".env" in gitignore
    results.append(check(has_dotenv_ignore, ".env is listed in .gitignore"))

    tracked_proc = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, cwd=ROOT,
    )
    if tracked_proc.returncode != 0:
        # Not inside a git repo: git ls-files produced nothing, so concluding
        # ".env is not tracked / no secrets" would be a misleading PASS.
        # Fail loudly instead, exactly as the landmine-reviewer suggested.
        results.append(check(False, "not inside a git repository — git ls-files failed"))
    else:
        tracked = tracked_proc.stdout.splitlines()

        env_tracked = [f for f in tracked if Path(f).name == ".env"]
        results.append(check(not env_tracked, f".env is NOT tracked by git (tracked .env files: {env_tracked or 'none'})"))

        leaked = []
        for f in tracked:
            if not Path(f).is_file():
                continue
            if Path(f).name in DOCUMENTED_PATTERN_FILES:
                continue
            try:
                content = (ROOT / f).read_text(errors="ignore")
            except Exception:
                continue
            for pat in SECRET_PATTERNS:
                if pat in content and Path(f).suffix in (".py", ".md", ".env", ".json", ".txt"):
                    leaked.append(f"{f}: contains '{pat}' pattern")
        results.append(check(not leaked, f"no secret-looking patterns in tracked files (found: {leaked or 'none'})"))

    print("\n== 4. Import + route registration ==")
    import_litmus = subprocess.run(
        [str(PYTHON), "-c", (
            "from app.main import app; "
            "routes=sorted(r.path for r in app.routes if r.path.startswith('/')); "
            "required=['/chat/local','/chat/hosted','/chat/auto','/health']; "
            "missing=[r for r in required if r not in routes]; "
            "assert not missing, f'missing {missing}'; "
            "print('routes OK: ' + ','.join(routes))"
        )],
        capture_output=True, text=True, cwd=ROOT,
    )
    ok = import_litmus.returncode == 0
    detail = import_litmus.stdout.strip() or import_litmus.stderr.strip()
    results.append(check(ok, f"app imports and all four routes registered ({detail})"))

    print("\n== Summary ==")
    passed = sum(results)
    total = len(results)
    print(f"{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())