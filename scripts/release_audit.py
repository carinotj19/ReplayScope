"""Reproducible pre-release checks; no database or network access needed.

This is a narrow safety net, NOT a substitute for professional secret scanning,
dependency auditing, vulnerability testing, or public deployment review.
"""
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def check():
    errors = []
    with (ROOT / "pyproject.toml").open("rb") as handle:
        metadata = tomllib.load(handle)["project"]
    version = metadata["version"]

    spec = json.loads((ROOT / "src/replayscope/openapi.json").read_text(encoding="utf-8"))
    if spec["info"]["version"] != version:
        errors.append("OpenAPI version disagrees with pyproject.toml")
    if spec["openapi"] != "3.1.0":
        errors.append("Expected OpenAPI 3.1.0")
    if not spec["paths"].get("/api/v1/experiments/{experiment_id}/compare"):
        errors.append("Paired-comparison API is absent from the contract")

    required = [
        "src/replayscope/__init__.py",
        "src/replayscope/demo.py",
        "src/replayscope/jobs.py",
        "src/replayscope/security.py",
        "src/replayscope/static/styles.css",
        "src/replayscope/templates/home.html",
        "src/replayscope/templates/comparison.html",
        "docs/portfolio-demo.md",
        "docs/deployment-readiness.md",
        "docs/release-v1.md",
        "tests/test_security.py",
        "tests/test_infrastructure.py",
        "tests/test_leases.py",
    ]
    for path in required:
        if not (ROOT / path).is_file():
            errors.append(f"Missing release material: {path}")

    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=ROOT, check=True,
        capture_output=True,
    ).stdout.decode("utf-8").split("\0")
    tracked = [entry for entry in tracked if entry]

    forbidden = (".env", ".env.local", "instance/", ".venv/")
    for path in tracked:
        if path in forbidden[:2] or path.startswith(forbidden[2:]) or path.endswith((".sqlite", ".sqlite3", ".db", ".pem", ".key")):
            errors.append(f"Runtime or secret material tracked: {path}")

    signatures = {
        "private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "GitHub personal token": re.compile(r"gh" + r"[pousr]_[A-Za-z0-9]{30,}"),
        "AWS access key ID": re.compile(r"AK" + r"IA[0-9A-Z]{16}"),
        "OpenAI-style secret key": re.compile(r"sk-" + r"[A-Za-z0-9_-]{40,}"),
    }
    scanned = 0
    for path in tracked:
        raw = (ROOT / path).read_bytes()
        if b"\x00" in raw:
            continue
        scanned += 1
        content = raw.decode("utf-8", errors="replace")
        for label, pattern in signatures.items():
            if pattern.search(content):
                errors.append(f"Possible {label} in {path}")

    if errors:
        for error in errors:
            print("FAIL:", error, file=sys.stderr)
        return 1
    print(f"PASS: ReplayScope v{version} contract, release files and {scanned} tracked text files checked")
    print("Reminder: heuristic credential checks do not prove a repository is safe to publish.")
    return 0


if __name__ == "__main__":
    sys.exit(check())
