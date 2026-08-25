"""Fail when operational data or common database/workbook files enter Git.

This check inspects tracked files plus untracked files that are not ignored.
Private operational files may exist locally under ignored paths, but they must
never become commit candidates.
"""

from __future__ import annotations

import subprocess
from pathlib import PurePosixPath


ALLOWED_DATA_FILES = {"data/README.md"}
SENSITIVE_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".xls", ".xlsx"}


def candidate_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [item for item in result.stdout.decode("utf-8").split("\0") if item]


def main() -> None:
    violations: list[str] = []
    for path in candidate_files():
        normalized = path.replace("\\", "/")
        suffix = PurePosixPath(normalized).suffix.casefold()
        if normalized.startswith("data/") and normalized not in ALLOWED_DATA_FILES:
            violations.append(normalized)
        elif suffix in SENSITIVE_SUFFIXES:
            violations.append(normalized)

    if violations:
        joined = "\n  - ".join(sorted(set(violations)))
        raise SystemExit(
            "[GAGAL] Berkas operasional/sensitif masih terlacak Git:\n"
            f"  - {joined}\n"
            "Keluarkan dari index dan provision berkas melalui kanal privat."
        )

    print("[OK] Kandidat commit tidak memuat data operasional, database, atau workbook.")


if __name__ == "__main__":
    main()
