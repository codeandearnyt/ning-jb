"""Deterministic analysis.

Analysts read data they are given and return findings. They never touch the
machine, a database, a model or an executor, so nothing in this package can
change the system it is describing.
"""

from __future__ import annotations

from ningx.analysis.analysts import AnalysisInput, run_analysts
from ningx.analysis.junk import (
    JunkReport,
    JunkRoot,
    JunkScanner,
    JunkScannerPort,
    NullJunkScanner,
    default_junk_roots,
)
from ningx.analysis.runner import ScanRepository, ScanRequest, ScanRunner

__all__ = [
    "AnalysisInput",
    "JunkReport",
    "JunkRoot",
    "JunkScanner",
    "JunkScannerPort",
    "NullJunkScanner",
    "ScanRepository",
    "ScanRequest",
    "ScanRunner",
    "default_junk_roots",
    "run_analysts",
]
