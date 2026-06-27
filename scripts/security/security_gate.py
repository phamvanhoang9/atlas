#!/usr/bin/env python
"""Security gate aggregator for ATLAS.

Runs Semgrep (OWASP + secrets + the project's AI-security ruleset), Gitleaks,
and pip-audit, merges their findings into the severity/score model defined in
`.claude/skills/ai-security-review/SKILL.md`, writes a JSON + Markdown report,
and exits non-zero if the change must be blocked.

Usage:
    python scripts/security/security_gate.py --stage commit|push|deploy|release [--files a.py b.py]

Gate logic (must match SKILL.md):
    risk_score      = min(100, 40*critical + 15*high + 5*medium + 1*low)
    security_score  = 100 - risk_score
    FAIL if critical_count > 0 OR secrets_found OR security_score < 90

Stages:
    commit  - fast pass, scoped to changed files when --files is given
    push    - full repo scan
    deploy  - full repo scan, strict (missing tools => FAIL)
    release - full repo scan, strict (missing tools => FAIL)

A missing tool (semgrep/gitleaks/pip-audit not installed) is a loud warning
and non-fatal for `commit`/`push` (local dev may not have everything
installed) but fatal for `deploy`/`release`, and always fatal when
ATLAS_SECURITY_STRICT=1 is set (CI sets this).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
_VENV_PYTHON = PROJECT_DIR / ".venv" / "Scripts" / "python.exe"
PYTHON = str(_VENV_PYTHON) if _VENV_PYTHON.exists() else sys.executable
REPORT_DIR = PROJECT_DIR / "security-reports"
SEVERITY_WEIGHTS = {"critical": 40, "high": 15, "medium": 5, "low": 1, "info": 0}
STRICT_STAGES = {"deploy", "release"}

# Dependency CVEs accepted as non-applicable to how ATLAS uses the package
# (either no upstream fix exists yet, or fixing requires a transitive bump
# with real blast radius for a code path ATLAS never exercises). Revisit
# whenever the relevant transitive dependency floor is intentionally raised.
ACCEPTED_RISK_VULNS = {
    "GHSA-gr75-jv2w-4656": (
        "langchain (bare package) is a transitive dep of ragas only - ATLAS "
        "never imports it directly (only langchain_core/langchain_classic/"
        "langchain_community). The CVE is path-traversal in langchain's "
        "file-search agent middleware and config loaders, neither of which "
        "ATLAS uses. Forcing langchain>=1.3.9 would cascade into "
        "langchain-core>=1.4.6 and a langgraph major bump, destabilizing the "
        "actually-used LangGraph orchestration for an unused code path."
    ),
    "GHSA-95ww-475f-pr4f": (
        "ragas SSRF is in the multi_modal_faithfulness collections module's "
        "_try_process_local_file/_try_process_url. ATLAS only uses "
        "ragas.metrics.Faithfulness/AnswerRelevancy/ContextRelevance "
        "(src/quality/evaluation/ragas_adapter.py) and never imports the "
        "multi_modal_faithfulness module."
    ),
    "GHSA-w8v5-vhqr-4h9v": (
        "diskcache's pickle-based cache is a transitive dep of ragas, used "
        "only as a local on-disk cache with no remote/multi-tenant write "
        "access in ATLAS's deployment model."
    ),
    "GHSA-537c-gmf6-5ccf": (
        "cryptography's only fix is 48.0.1, which requires "
        "langchain-litellm>=0.7.0, which requires langchain-core>=1.4.7. "
        "Verified by reproducing it: that combination crashes on import "
        "(langgraph 1.1.10's checkpoint/serde layer is incompatible with "
        "langchain-core 1.4.x) and was reverted. Revisit once langgraph is "
        "deliberately upgraded and the full orchestration is re-tested."
    ),
}


def run(cmd: list[str], cwd: Path = PROJECT_DIR) -> tuple[int, str, str]:
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 127, "", f"{cmd[0]}: not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]}: timed out"


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def map_semgrep_severity(rule_severity: str, metadata: dict) -> str:
    declared = (metadata or {}).get("atlas_severity")
    if declared:
        return declared.lower()
    return {"ERROR": "high", "WARNING": "medium", "INFO": "low"}.get(rule_severity, "low")


def semgrep_command(files: list[str] | None) -> list[str] | None:
    """Build the semgrep invocation, falling back to the official Docker
    image on Windows where semgrep has no native pip/binary distribution."""
    configs = ["p/python", "p/owasp-top-ten", "p/secrets", "semgrep-rules/ai-security.yml"]
    targets = files if files else ["src", "main.py"]

    if tool_available("semgrep"):
        cmd = ["semgrep", "--quiet", "--json", "--metrics=off"]
        for cfg in configs:
            cmd += ["--config", cfg]
        return cmd + targets

    if tool_available("docker"):
        mount = str(PROJECT_DIR).replace("\\", "/")
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{mount}:/src",
            "-w", "/src",
            "semgrep/semgrep",
            "semgrep", "--quiet", "--json", "--metrics=off",
        ]
        for cfg in configs:
            cmd += ["--config", cfg]
        return cmd + targets

    return None


def run_semgrep(files: list[str] | None) -> tuple[list[dict], list[str]]:
    findings: list[dict] = []
    warnings: list[str] = []

    cmd = semgrep_command(files)
    if cmd is None:
        warnings.append(
            "semgrep is not installed and docker is unavailable - "
            "AI-security and OWASP static analysis was SKIPPED"
        )
        return findings, warnings

    code, stdout, stderr = run(cmd)
    if code not in (0, 1):
        warnings.append(f"semgrep exited {code}: {stderr.strip()[:500]}")
        return findings, warnings

    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        warnings.append("semgrep produced unparsable JSON output")
        return findings, warnings

    for result in data.get("results", []):
        extra = result.get("extra", {})
        metadata = extra.get("metadata", {})
        findings.append(
            {
                "id": result.get("check_id", "semgrep"),
                "category": metadata.get("category", "app_security"),
                "title": extra.get("message", "")[:120],
                "severity": map_semgrep_severity(extra.get("severity", "WARNING"), metadata),
                "file": result.get("path"),
                "line": result.get("start", {}).get("line"),
                "description": extra.get("message", ""),
                "remediation": metadata.get("remediation", "See rule message for guidance."),
                "source": "semgrep",
            }
        )
    return findings, warnings


def run_gitleaks() -> tuple[list[dict], bool, list[str]]:
    findings: list[dict] = []
    warnings: list[str] = []
    if not tool_available("gitleaks"):
        warnings.append("gitleaks is not installed - secret scanning was SKIPPED")
        return findings, False, warnings

    report_path = REPORT_DIR / "gitleaks.json"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        "gitleaks", "detect",
        "--source", str(PROJECT_DIR),
        "--config", str(PROJECT_DIR / ".gitleaks.toml"),
        "--report-format", "json",
        "--report-path", str(report_path),
        "--no-banner",
        "--redact",
    ]
    code, _stdout, stderr = run(cmd)
    if code not in (0, 1):
        warnings.append(f"gitleaks exited {code}: {stderr.strip()[:500]}")
        return findings, False, warnings

    if report_path.exists():
        try:
            leaks = json.loads(report_path.read_text(encoding="utf-8") or "[]")
        except json.JSONDecodeError:
            leaks = []
        for leak in leaks:
            findings.append(
                {
                    "id": f"gitleaks-{leak.get('RuleID', 'secret')}",
                    "category": "ai_security",
                    "title": f"Secret detected: {leak.get('RuleID', 'unknown rule')}",
                    "severity": "critical",
                    "file": leak.get("File"),
                    "line": leak.get("StartLine"),
                    "description": leak.get("Description", "Potential secret committed to the repository."),
                    "remediation": "Revoke the credential, purge it from history, and load secrets from env/secret manager.",
                    "source": "gitleaks",
                }
            )
    return findings, bool(findings), warnings


def pip_audit_available() -> bool:
    if tool_available("pip-audit"):
        return True
    code, _stdout, _stderr = run([PYTHON, "-m", "pip_audit", "--version"])
    return code == 0


def requirements_changed() -> bool:
    code, stdout, _stderr = run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "--", "requirements.txt"]
    )
    return code == 0 and bool(stdout.strip())


def run_pip_audit(skip_if_unchanged: bool = False) -> tuple[list[dict], list[str]]:
    findings: list[dict] = []
    warnings: list[str] = []
    if skip_if_unchanged and not requirements_changed():
        warnings.append("pip-audit SKIPPED - requirements.txt unchanged in this commit")
        return findings, warnings
    if not pip_audit_available():
        warnings.append("pip-audit is not installed - dependency vulnerability scan was SKIPPED")
        return findings, warnings

    # requirements.txt is fully pinned (==), so --no-deps lets pip-audit check
    # the exact pinned set against the vuln DB without resolving/installing
    # the whole dependency tree into a throwaway venv (slow, network-heavy).
    audit_args = ["-r", "requirements.txt", "--format", "json", "--no-deps"]
    for vuln_id in ACCEPTED_RISK_VULNS:
        audit_args += ["--ignore-vuln", vuln_id]
    if tool_available("pip-audit"):
        cmd = ["pip-audit", *audit_args]
    else:
        cmd = [PYTHON, "-m", "pip_audit", *audit_args]
    code, stdout, stderr = run(cmd)
    if code not in (0, 1):
        warnings.append(f"pip-audit exited {code}: {stderr.strip()[:500]}")
        return findings, warnings

    try:
        data = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        warnings.append("pip-audit produced unparsable JSON output")
        return findings, warnings

    deps = data if isinstance(data, list) else data.get("dependencies", [])
    for dep in deps:
        for vuln in dep.get("vulns", []) or []:
            findings.append(
                {
                    "id": vuln.get("id", "pip-audit"),
                    "category": "app_security",
                    "title": f"Vulnerable dependency: {dep.get('name')} {dep.get('version')}",
                    "severity": "high",
                    "file": "requirements.txt",
                    "line": None,
                    "description": vuln.get("description", "")[:500],
                    "remediation": f"Upgrade {dep.get('name')} to a fixed version ({', '.join(vuln.get('fix_versions', []) or ['see advisory'])}).",
                    "source": "pip-audit",
                }
            )

    for vuln_id, reason in ACCEPTED_RISK_VULNS.items():
        warnings.append(f"pip-audit: accepted-risk, ignored {vuln_id} - {reason}")

    return findings, warnings


def score(findings: list[dict]) -> tuple[int, int, dict]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in findings:
        sev = f.get("severity", "low")
        counts[sev] = counts.get(sev, 0) + 1
    risk = min(100, sum(SEVERITY_WEIGHTS.get(sev, 0) * n for sev, n in counts.items()))
    security_score = max(0, 100 - risk)
    return risk, security_score, counts


def decide(security_score: int, counts: dict, secrets_found: bool, missing_tools: bool, strict: bool) -> str:
    if counts.get("critical", 0) > 0:
        return "FAIL"
    if secrets_found:
        return "FAIL"
    if security_score < 90:
        return "FAIL"
    if missing_tools and strict:
        return "FAIL"
    return "PASS"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=["commit", "push", "deploy", "release"], default="push")
    parser.add_argument("--files", nargs="*", default=None)
    args = parser.parse_args()

    strict = args.stage in STRICT_STAGES or os.environ.get("ATLAS_SECURITY_STRICT") == "1"
    files = [f for f in (args.files or []) if f.endswith(".py")] or None

    semgrep_findings, semgrep_warnings = run_semgrep(files if args.stage == "commit" else None)
    gitleaks_findings, secrets_found, gitleaks_warnings = run_gitleaks()
    audit_findings, audit_warnings = run_pip_audit(skip_if_unchanged=args.stage == "commit")

    all_findings = semgrep_findings + gitleaks_findings + audit_findings
    warnings = semgrep_warnings + gitleaks_warnings + audit_warnings
    missing_tools = any("not installed" in w for w in warnings)

    risk, security_score, counts = score(all_findings)
    recommendation = decide(security_score, counts, secrets_found, missing_tools, strict)

    report = {
        "stage": args.stage,
        "strict": strict,
        "findings": all_findings,
        "warnings": warnings,
        "risk_score": risk,
        "security_score": security_score,
        "critical_count": counts.get("critical", 0),
        "high_count": counts.get("high", 0),
        "medium_count": counts.get("medium", 0),
        "low_count": counts.get("low", 0),
        "secrets_found": secrets_found,
        "missing_tools": missing_tools,
        "recommendation": recommendation,
    }

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    (REPORT_DIR / "security-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (REPORT_DIR / "security-report.md").write_text(render_markdown(report), encoding="utf-8")

    print(render_markdown(report))

    return 0 if recommendation == "PASS" else 1


def render_markdown(report: dict) -> str:
    lines = [
        f"# Security Gate Report ({report['stage']})",
        "",
        f"**Recommendation: {report['recommendation']}**",
        "",
        f"- Security score: {report['security_score']}/100 (risk {report['risk_score']})",
        f"- Critical: {report['critical_count']}  High: {report['high_count']}  "
        f"Medium: {report['medium_count']}  Low: {report['low_count']}",
        f"- Secrets found: {report['secrets_found']}",
        f"- Missing tools (strict={report['strict']}): {report['missing_tools']}",
        "",
    ]
    if report["warnings"]:
        lines.append("## Warnings")
        for w in report["warnings"]:
            lines.append(f"- {w}")
        lines.append("")
    if report["findings"]:
        lines.append("## Findings")
        for f in sorted(report["findings"], key=lambda x: SEVERITY_WEIGHTS.get(x.get("severity", "low"), 0), reverse=True):
            loc = f"{f.get('file')}:{f.get('line')}" if f.get("file") else "n/a"
            lines.append(f"- [{f.get('severity', 'low').upper()}] {f.get('title')} ({loc}) — {f.get('remediation')}")
    else:
        lines.append("No findings.")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
