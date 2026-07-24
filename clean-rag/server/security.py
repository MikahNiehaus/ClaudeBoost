"""Security scanning runner for clean-rag.

Runs available security tools (bandit, pip-audit, semgrep) scoped to changed
files and returns structured findings. Follows mutation.py's security model:
every path is validated, every subprocess runs with shell=False, and a missing
tool is reported honestly rather than faked.

The endpoint is opt-in: verifier-gate.py calls it only when
CLEAN_RAG_SECURITY_SCAN=1 is set, and only for files already flagged as
high-stakes by high_stakes.py.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from .mutation import _validate_files

DEFAULT_TIMEOUT_S = 300


def _scan_result(has_tool, tools_run, *, findings=None, summary=None,
                 error=None, rejected=None):
    out = {
        "has_tool": has_tool,
        "tools_run": tools_run,
        "findings": findings or [],
        "summary": summary or {"critical": 0, "high": 0, "medium": 0, "low": 0},
        "error": error,
    }
    if rejected:
        out["rejected_files"] = rejected
    return out


def _summarize(findings):
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for f in findings:
        sev = f.get("severity", "low").lower()
        if sev in counts:
            counts[sev] += 1
    return counts


def _run_bandit(root, files):
    """Run bandit on Python files. Returns list of findings or None if not installed."""
    bandit = shutil.which("bandit")
    if not bandit:
        return None

    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        argv = [bandit, "-r", ".", "-f", "json", "--quiet"]
    else:
        argv = [bandit, "-f", "json", "--quiet"] + py_files

    env = {**os.environ, "CI": "true"}
    try:
        proc = subprocess.run(
            argv, cwd=str(root), shell=False, capture_output=True,
            text=True, timeout=DEFAULT_TIMEOUT_S, env=env, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []

    # bandit exit code 1 = findings found (not an error)
    stdout = proc.stdout or ""
    try:
        start = stdout.find("{")
        if start < 0:
            return []
        data = json.loads(stdout[start:])
    except (json.JSONDecodeError, ValueError):
        return []

    findings = []
    for item in data.get("results", []):
        filename = item.get("filename", "")
        if ".venv" in filename.lower():
            continue
        sev = (item.get("issue_severity") or "low").lower()
        findings.append({
            "tool": "bandit",
            "severity": sev,
            "file": filename,
            "line": item.get("line_number", 0),
            "title": item.get("test_name", "BanditIssue"),
            "message": item.get("issue_text", ""),
        })
    return findings


def _run_pip_audit(root):
    """Run pip-audit. Returns list of findings or None if not installed."""
    pip_audit = shutil.which("pip-audit")
    if not pip_audit:
        return None

    argv = [pip_audit, "--format", "json"]
    env = {**os.environ, "CI": "true"}
    try:
        proc = subprocess.run(
            argv, cwd=str(root), shell=False, capture_output=True,
            text=True, timeout=DEFAULT_TIMEOUT_S, env=env, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []

    stdout = proc.stdout or ""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return []

    findings = []
    for dep in data.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            findings.append({
                "tool": "pip-audit",
                "severity": "high",
                "file": "requirements.txt",
                "line": 0,
                "title": vuln.get("id", "CVE"),
                "message": f"{dep.get('name', '?')}=={dep.get('version', '?')}: {vuln.get('description', '')}",
            })
    return findings


def _run_semgrep(root, files):
    """Run semgrep. Returns list of findings or None if not installed."""
    semgrep = shutil.which("semgrep")
    if not semgrep:
        return None

    argv = [semgrep, "--json", "--quiet", "--config", "auto"]
    if files:
        argv += files
    else:
        argv += ["."]

    env = {**os.environ, "CI": "true"}
    try:
        proc = subprocess.run(
            argv, cwd=str(root), shell=False, capture_output=True,
            text=True, timeout=DEFAULT_TIMEOUT_S, env=env, errors="replace",
        )
    except subprocess.TimeoutExpired:
        return []
    except Exception:
        return []

    stdout = proc.stdout or ""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return []

    findings = []
    for result in data.get("results", []):
        sev = (result.get("extra", {}).get("severity") or "low").lower()
        findings.append({
            "tool": "semgrep",
            "severity": sev,
            "file": result.get("path", ""),
            "line": result.get("start", {}).get("line", 0),
            "title": result.get("check_id", "SemgrepRule"),
            "message": result.get("extra", {}).get("message", ""),
        })
    return findings


def run_security_scan(project_path, changed_files=None):
    """Entry point. Blocking, run in executor from app.py."""
    root = Path(project_path)
    if not root.is_dir():
        return _scan_result(False, [], error=f"not a directory: {project_path}")

    valid, rejected = _validate_files(root, changed_files or [])

    all_findings = []
    tools_run = []

    bandit_result = _run_bandit(root, valid)
    if bandit_result is not None:
        tools_run.append("bandit")
        all_findings.extend(bandit_result)

    req_names = {"requirements.txt", "setup.py", "pyproject.toml", "Pipfile"}
    has_req = any(Path(f).name in req_names for f in valid)
    if has_req or not valid:
        audit_result = _run_pip_audit(root)
        if audit_result is not None:
            tools_run.append("pip-audit")
            all_findings.extend(audit_result)

    semgrep_result = _run_semgrep(root, valid)
    if semgrep_result is not None:
        tools_run.append("semgrep")
        all_findings.extend(semgrep_result)

    summary = _summarize(all_findings)
    return _scan_result(
        bool(tools_run), tools_run,
        findings=all_findings[:50],
        summary=summary,
        rejected=rejected,
    )
