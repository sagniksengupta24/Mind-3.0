"""Verdict computation and machine-readable JSON report."""

from __future__ import annotations

from . import __version__
from .clocks import assign_domains
from .crossings import analyze
from .parser import InputError, load_top
from .synchronizers import Verdict, classify

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_INCONCLUSIVE = 2
EXIT_ERROR = 3


def run_checker(rtl_path: str, top: str) -> tuple[int, dict]:
    """Run the full checker; return (exit_code, report_dict). Never raises."""
    try:
        module = load_top(rtl_path, top)
    except InputError as exc:
        return EXIT_ERROR, _error_report(top, str(exc))
    except Exception as exc:  # fail closed on anything unexpected
        return EXIT_ERROR, _error_report(top, f"internal error: {exc}")
    try:
        domain_map = assign_domains(module)
        analysis = analyze(module, domain_map)
        verdict = classify(module, domain_map, analysis)
    except InputError as exc:
        return EXIT_ERROR, _error_report(top, str(exc))
    except Exception as exc:  # fail closed on anything unexpected
        return EXIT_ERROR, _error_report(top, f"internal error: {exc}")
    return _verdict_exit(verdict), _verdict_report(top, module.name, verdict)


def _verdict_exit(verdict: Verdict) -> int:
    if verdict.status == "PASS":
        return EXIT_PASS
    if verdict.status == "FAIL":
        return EXIT_FAIL
    return EXIT_INCONCLUSIVE


def _verdict_report(top: str, module_name: str, verdict: Verdict) -> dict:
    return {
        "status": verdict.status,
        "tool": "structural_cdc_checker",
        "tool_version": __version__,
        "top": top,
        "module": module_name,
        "crossings": [
            {
                "source": c.source,
                "source_clock": c.source_domain,
                "destination": c.destination,
                "destination_clock": c.destination_domain,
                "path": c.path,
                "classification": c.classification,
                "severity": c.severity,
                "detail": c.detail,
            }
            for c in verdict.crossings
        ],
        "notes": list(verdict.notes),
    }


def _error_report(top: str, message: str) -> dict:
    return {
        "status": "ERROR",
        "tool": "structural_cdc_checker",
        "tool_version": __version__,
        "top": top,
        "module": None,
        "crossings": [],
        "notes": [message],
    }
