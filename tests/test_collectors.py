"""Read-only collectors: junk measurement and startup inventory parsing.

The junk scanner is tested against a real temporary tree because its whole job
is filesystem behaviour: symlinks, unreadable files, limits. It must never
report a number it did not measure, and it must never leave the roots it was
given.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from ningx.analysis.junk import (
    JunkScanner,
    NullJunkScanner,
    default_junk_roots,
)
from ningx.security.startup_collector import (
    FakeStartupCollector,
    StartupEntry,
    parse_executable,
)


def write(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)


def test_scanner_measures_every_file_in_the_tree(tmp_path: Path) -> None:
    write(tmp_path / "a.tmp", 100)
    write(tmp_path / "nested" / "b.tmp", 250)
    report = JunkScanner([tmp_path]).scan()
    assert report.total_bytes == 350
    assert report.total_files == 2
    assert report.limit_hit is False
    assert report.roots[0].path == str(tmp_path)


def test_scanner_reports_per_root_totals(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    write(first / "a.bin", 10)
    write(second / "b.bin", 20)
    write(second / "c.bin", 30)
    report = JunkScanner([first, second]).scan()
    assert [(Path(root.path).name, root.bytes) for root in report.roots] == [
        ("one", 10),
        ("two", 50),
    ]


def test_file_budget_stops_the_walk_and_says_so(tmp_path: Path) -> None:
    for index in range(20):
        write(tmp_path / f"file{index}.tmp", 10)
    report = JunkScanner([tmp_path], max_files=5).scan()
    assert report.total_files == 5
    assert report.limit_hit is True
    assert report.roots[0].truncated is True


def test_budget_is_shared_across_roots(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    for index in range(10):
        write(first / f"a{index}.tmp", 1)
        write(second / f"b{index}.tmp", 1)
    report = JunkScanner([first, second], max_files=4).scan()
    assert report.total_files == 4
    assert report.limit_hit is True
    # The second root is never entered once the budget is spent.
    assert len(report.roots) == 1


def test_a_missing_root_is_measured_as_empty_not_as_an_error(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist"
    report = JunkScanner([missing]).scan()
    assert report.total_bytes == 0
    assert report.total_files == 0
    assert report.errors == ()


def test_empty_tree_is_zero_and_not_a_finding(tmp_path: Path) -> None:
    report = JunkScanner([tmp_path]).scan()
    assert report.total_bytes == 0
    assert report.roots[0].files == 0


@pytest.mark.skipif(os.name != "nt", reason="junctions are a Windows feature")
def test_junction_is_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    write(outside / "huge.bin", 4096)
    root = tmp_path / "temp"
    root.mkdir()
    write(root / "real.tmp", 10)

    link = root / "link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not permitted for this user")

    report = JunkScanner([root]).scan()
    # Either the link is skipped entirely (junction/symlink) or the walk never
    # leaves the root; in both cases the 4096-byte file must not be counted.
    assert report.total_bytes == 10


def test_null_scanner_reports_nothing_scanned() -> None:
    report = NullJunkScanner().scan()
    assert report.roots == ()
    assert report.total_bytes == 0
    assert report.scanned_at is not None


def test_default_roots_exist_and_are_unique() -> None:
    roots = default_junk_roots()
    assert all(root.is_dir() for root in roots)
    assert len({str(root).lower() for root in roots}) == len(roots)


# ------------------------------------------------------------------ parsing


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        (r'"C:\Program Files\App\app.exe" --silent', r"C:\Program Files\App\app.exe"),
        (r"C:\Apps\app.exe -min", r"C:\Apps\app.exe"),
        (r'"C:\Apps\app.exe"', r"C:\Apps\app.exe"),
        (r"  C:\Apps\app.exe  ", r"C:\Apps\app.exe"),
        ("", None),
        ("   ", None),
    ],
)
def test_parse_executable(command: str, expected: str | None) -> None:
    assert parse_executable(command) == expected


def test_parse_executable_expands_environment_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NingXTestRoot", r"C:\Apps")
    assert parse_executable(r"%NingXTestRoot%\app.exe") == r"C:\Apps\app.exe"


def test_parse_executable_keeps_a_host_process_command() -> None:
    command = r"rundll32.exe C:\Windows\System32\shell32.dll,Control_RunDLL"
    assert parse_executable(command) == "rundll32.exe"


def test_parse_executable_handles_an_unterminated_quote() -> None:
    assert parse_executable(r'"C:\Apps\app.exe') == r"C:\Apps\app.exe"


def test_fake_collector_returns_a_copy() -> None:
    entry = StartupEntry(
        name="App",
        command=r"C:\Apps\app.exe",
        location=r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
        scope="current user",
        enabled=True,
        executable=r"C:\Apps\app.exe",
        exists=True,
    )
    collector = FakeStartupCollector([entry])
    first = collector.collect()
    first.clear()
    assert collector.collect() == [entry]


def test_startup_fingerprint_subject_is_case_insensitive() -> None:
    upper = StartupEntry(
        name="App",
        command="",
        location=r"HKCU\Run",
        scope="current user",
        enabled=True,
    )
    lower = StartupEntry(
        name="app",
        command="",
        location=r"hkcu\run",
        scope="current user",
        enabled=True,
    )
    assert upper.fingerprint_subject == lower.fingerprint_subject
