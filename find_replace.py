#!/usr/bin/env python3
"""
find_replace.py - Interactive Find & Replace CLI for Termux / Android 15.

A single-file, dependency-free tool that lets you search and replace text
across a single file or all files in the current directory, with preview,
confirmation, and optional backups before anything is modified.

Run:
    python find_replace.py
    python find_replace.py --find "hello" --replace "world"
    python find_replace.py --file example.txt --find "hello" --replace "world"
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

IGNORED_DIRS = {".git", "__pycache__", ".hg", ".svn", "node_modules", ".venv"}

IGNORED_SUFFIXES = {
    ".pyc", ".pyo", ".so", ".o", ".class", ".jar", ".exe", ".dll",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp",
    ".mp3", ".mp4", ".mov", ".avi", ".zip", ".tar", ".gz", ".7z",
    ".pdf", ".sqlite", ".db",
    ".bak", ".swp", ".swo", ".tmp",
}

IGNORED_NAMES = {".DS_Store"}

MAX_PREVIEW_LINES_PER_FILE = 12
MAX_PREVIEW_FILES = 5

ENCODINGS_TO_TRY = ("utf-8", "utf-8-sig", "latin-1")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class SearchParams:
    find: str
    replace: str
    mode: str = "literal"
    compiled: Optional[re.Pattern] = None

    def build_pattern(self) -> None:
        """Compile the regex pattern used internally for all modes."""
        if self.mode == "regex":
            self.compiled = re.compile(self.find)
        elif self.mode == "icase":
            self.compiled = re.compile(re.escape(self.find), re.IGNORECASE)
        else:
            self.compiled = re.compile(re.escape(self.find))


@dataclass
class FileScanResult:
    path: Path
    encoding: str
    original_text: str
    new_text: str
    match_count: int
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class RunSummary:
    files_changed: int = 0
    total_replacements: int = 0
    failures: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------

class Cancelled(Exception):
    """Raised when the user cancels the current operation (Ctrl+C / Ctrl+D)."""


def prompt(text: str) -> str:
    """Read a line of input, raising Cancelled on Ctrl+C / Ctrl+D."""
    try:
        return input(text)
    except (KeyboardInterrupt, EOFError):
        print()
        raise Cancelled()


def confirm(question: str, default_yes: bool = False) -> bool:
    """Ask a yes/no question. Enter alone follows `default_yes`."""
    suffix = "[Y/n]" if default_yes else "[y/N]"
    answer = prompt(f"{question} {suffix}: ").strip().lower()
    if not answer:
        return default_yes
    return answer in ("y", "yes")


def is_probably_binary(sample: bytes) -> bool:
    """Heuristic: presence of a NUL byte usually means binary content."""
    return b"\x00" in sample


def read_text_file(path: Path) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Try to read a file as text."""
    try:
        with path.open("rb") as f:
            sample = f.read(8192)
    except PermissionError:
        return None, None, "Permission denied"
    except OSError as exc:
        return None, None, f"Could not read file: {exc}"

    if is_probably_binary(sample):
        return None, None, "Binary file (skipped)"

    for encoding in ENCODINGS_TO_TRY:
        try:
            text = path.read_text(encoding=encoding)
            return text, encoding, None
        except (UnicodeDecodeError, LookupError):
            continue
        except PermissionError:
            return None, None, "Permission denied"
        except OSError as exc:
            return None, None, f"Could not read file: {exc}"

    return None, None, "Could not decode file with supported encodings"


def should_ignore(path: Path) -> bool:
    """Decide whether a path should be skipped during 'all files' scans."""
    if path.name in IGNORED_NAMES:
        return True
    if path.suffix.lower() in IGNORED_SUFFIXES:
        return True
    if path.name.endswith("~"):
        return True
    for part in path.parts:
        if part in IGNORED_DIRS:
            return True
    return False


# ---------------------------------------------------------------------------
# Scanning
# ---------------------------------------------------------------------------

def scan_file(path: Path, params: SearchParams) -> FileScanResult:
    """Read a file and compute what its content would look like after replacement."""
    if not path.exists():
        return FileScanResult(path, "", "", "", 0, error="File not found")
    if path.is_symlink():
        return FileScanResult(path, "", "", "", 0, error="Symlink (skipped)")
    if not path.is_file():
        return FileScanResult(path, "", "", "", 0, error="Not a regular file")

    text, encoding, err = read_text_file(path)
    if err is not None:
        return FileScanResult(path, "", "", "", 0, error=err)

    assert text is not None and encoding is not None
    new_text, count = params.compiled.subn(params.replace, text)
    return FileScanResult(path, encoding, text, new_text, count)


def gather_candidate_files(directory: Path, recursive: bool) -> list[Path]:
    """List candidate files in a directory, honoring ignore rules."""
    files: list[Path] = []
    iterator = directory.rglob("*") if recursive else directory.iterdir()
    for entry in iterator:
        try:
            if entry.is_symlink() or entry.is_dir() or not entry.is_file():
                continue
        except OSError:
            continue
        if should_ignore(entry.relative_to(directory) if recursive else entry):
            continue
        files.append(entry)
    return sorted(files)


# ---------------------------------------------------------------------------
# Preview / summary rendering
# ---------------------------------------------------------------------------

def preview_changes(results: list[FileScanResult]) -> None:
    """Print a unified-style diff preview, capped in size."""
    changed = [r for r in results if r.ok and r.match_count > 0]
    if not changed:
        print("\nNo changes to preview.")
        return

    print()
    for result in changed[:MAX_PREVIEW_FILES]:
        print(f"--- {result.path} ---\n")
        old_lines = result.original_text.splitlines()
        new_lines = result.new_text.splitlines()
        shown = 0
        for old_line, new_line in zip(old_lines, new_lines):
            if old_line != new_line:
                if shown >= MAX_PREVIEW_LINES_PER_FILE:
                    print("  ... (preview truncated) ...")
                    break
                print(f"- {old_line}")
                print(f"+ {new_line}")
                shown += 1
        print()

    if len(changed) > MAX_PREVIEW_FILES:
        print(f"... and {len(changed) - MAX_PREVIEW_FILES} more file(s) with changes not shown.\n")


def show_match_table(results: list[FileScanResult]) -> None:
    """Print the per-file match counts and total, before confirmation."""
    matched = [r for r in results if r.ok and r.match_count > 0]
    skipped_errors = [r for r in results if not r.ok]

    if not matched:
        print("\nNo matches found.")
    else:
        print(f"\nFound {len(matched)} matching file(s).\n")
        name_width = max(len(str(r.path)) for r in matched) + 2
        for i, r in enumerate(matched, start=1):
            word = "match" if r.match_count == 1 else "matches"
            print(f"{i}. {str(r.path):<{name_width}} {r.match_count} {word}")
        print(f"\nTotal replacements: {sum(r.match_count for r in matched)}")

    if skipped_errors:
        print(f"\n({len(skipped_errors)} file(s) skipped: binary, unreadable, or permission issues)")


# ---------------------------------------------------------------------------
# Backup / write
# ---------------------------------------------------------------------------

def create_backup(path: Path) -> Optional[Path]:
    """Create a .bak copy of a file without clobbering an existing backup."""
    backup_path = path.with_name(path.name + ".bak")
    counter = 1
    while backup_path.exists():
        backup_path = path.with_name(f"{path.name}.bak{counter}")
        counter += 1
    try:
        backup_path.write_bytes(path.read_bytes())
        return backup_path
    except OSError as exc:
        print(f"  ! Could not create backup for {path}: {exc}")
        return None


def write_result(result: FileScanResult, make_backup: bool) -> tuple[bool, Optional[str]]:
    """Write a scanned result's new content back to disk."""
    try:
        if make_backup and create_backup(result.path) is None:
            return False, "backup failed"
        result.path.write_text(result.new_text, encoding=result.encoding)
        return True, None
    except PermissionError:
        return False, "Permission denied (read-only file?)"
    except OSError as exc:
        return False, f"write failed: {exc}"


def verify_write(result: FileScanResult) -> bool:
    """Re-read the file after writing to confirm it matches the expected content."""
    try:
        return result.path.read_text(encoding=result.encoding) == result.new_text
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Interactive menus
# ---------------------------------------------------------------------------

def clear_line() -> None:
    print()


def show_menu() -> None:
    """Display the main menu banner."""
    print("╔════════════════════════════════════╗")
    print("║        FIND & REPLACE TOOL         ║")
    print("╚════════════════════════════════════╝")
    print("\nCurrent directory:")
    print(Path.cwd())
    print("\n1. Find & Replace")
    print("2. Exit")


def get_search_parameters(prefill_find: Optional[str] = None,
                           prefill_replace: Optional[str] = None) -> SearchParams:
    """Prompt for find/replace text and search mode."""
    find_text = prefill_find
    while not find_text:
        find_text = prompt("\nText to find: ")
        if not find_text:
            print("Search text cannot be empty.")

    replace_text = prefill_replace
    if replace_text is None:
        replace_text = prompt("Replace with: ")

    print("\nSearch mode:\n\n1. Literal\n2. Case-insensitive\n3. Regular expression")
    choice = prompt("Choose [1]: ").strip() or "1"
    mode = {"1": "literal", "2": "icase", "3": "regex"}.get(choice, "literal")

    params = SearchParams(find=find_text, replace=replace_text, mode=mode)
    try:
        params.build_pattern()
    except re.error as exc:
        print(f"\nInvalid regular expression: {exc}")
        raise Cancelled()
    return params


def list_files(directory: Path) -> list[Path]:
    """Return a sorted list of visible, non-ignored files directly in directory."""
    files = []
    try:
        for entry in sorted(directory.iterdir()):
            if entry.is_dir() or entry.is_symlink() or not entry.is_file():
                continue
            if not should_ignore(entry):
                files.append(entry)
    except PermissionError:
        print("Permission denied listing this directory.")
    return files


def choose_specific_file(directory: Path) -> Optional[Path]:
    """Let the user pick a file from a numbered list, or type a path manually."""
    files = list_files(directory)
    if files:
        print("\nFiles:\n")
        for i, f in enumerate(files, start=1):
            print(f"{i}. {f.name}")
        print("\nType a number, or enter a filename/path manually.")
    else:
        print("\nNo visible files found in this directory.")
        print("Enter a filename/path manually.")

    choice = prompt("Select file: ").strip()
    if not choice:
        return None
    if choice.isdigit():
        idx = int(choice)
        if 1 <= idx <= len(files):
            return files[idx - 1]
        print("Invalid selection.")
        return None

    candidate = Path(choice).expanduser()
    return candidate if candidate.is_absolute() else directory / candidate


def choose_target(directory: Path) -> Optional[tuple[str, Optional[Path], bool]]:
    """Ask where the replacement should be applied."""
    print("\nWhere should this be applied?\n\n1. Specific file\n2. All files in current directory\n3. Back")
    choice = prompt("Choose: ").strip()
    if choice == "1":
        chosen = choose_specific_file(directory)
        return None if chosen is None else ("file", chosen, False)
    if choice == "2":
        return ("all", None, confirm("Include subdirectories recursively?", default_yes=False))
    return None


# ---------------------------------------------------------------------------
# Core workflow
# ---------------------------------------------------------------------------

def run_find_replace_flow(directory: Path,
                           prefill_find: Optional[str] = None,
                           prefill_replace: Optional[str] = None,
                           prefill_file: Optional[Path] = None) -> None:
    """Run the full Input -> Scan -> Preview -> Confirm -> Modify -> Summary pipeline."""
    try:
        params = get_search_parameters(prefill_find, prefill_replace)
        if prefill_file is not None:
            target_kind, target_path, recursive = "file", prefill_file, False
        else:
            target = choose_target(directory)
            if target is None:
                return
            target_kind, target_path, recursive = target

        if target_kind == "file":
            assert target_path is not None
            if not target_path.exists():
                print(f"\nFile not found: {target_path}")
                return
            candidates = [target_path]
        else:
            candidates = gather_candidate_files(directory, recursive)
            if not candidates:
                print("\nNo files found to scan.")
                return

        results = [scan_file(p, params) for p in candidates]
        show_match_table(results)
        matched = [r for r in results if r.ok and r.match_count > 0]
        if not matched:
            return
        preview_changes(results)
        if not confirm("Apply these changes?", default_yes=False):
            print("\nCancelled. No files were modified.")
            return
        make_backup = confirm("Create backups before replacing?", default_yes=True)

        print("\nReplacing...\n")
        summary = RunSummary()
        name_width = max(len(str(r.path)) for r in matched) + 2
        for result in matched:
            success, err = write_result(result, make_backup)
            if not success:
                print(f"✗ {str(result.path):<{name_width}} failed ({err})")
                summary.failures.append((result.path, err))
                continue
            if not verify_write(result):
                print(f"✗ {str(result.path):<{name_width}} verification failed")
                summary.failures.append((result.path, "content mismatch after write"))
                continue
            word = "replacement" if result.match_count == 1 else "replacements"
            print(f"✓ {str(result.path):<{name_width}} {result.match_count} {word}")
            summary.files_changed += 1
            summary.total_replacements += result.match_count
        show_summary(summary)
    except Cancelled:
        print("\nCancelled by user. No files were modified.")


def show_summary(summary: RunSummary) -> None:
    """Print the final results of a replacement run."""
    print("\nDone.\n")
    print(f"{summary.total_replacements} replacements made in {summary.files_changed} file(s).")
    if summary.failures:
        print(f"\n{len(summary.failures)} file(s) failed:")
        for path, err in summary.failures:
            print(f"  - {path}: {err}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Interactive Find & Replace CLI for Termux.")
    parser.add_argument("--find", help="Text or pattern to search for.")
    parser.add_argument("--replace", help="Replacement text.", default="")
    parser.add_argument("--file", help="Operate on this specific file only.")
    return parser


def main() -> None:
    """Entry point: parse arguments and run the interactive loop."""
    args = build_arg_parser().parse_args()
    directory = Path.cwd()
    if args.find is not None:
        prefill_file = Path(args.file).expanduser() if args.file else None
        run_find_replace_flow(directory, args.find, args.replace, prefill_file)
        return

    while True:
        try:
            show_menu()
            choice = prompt("\nChoose an option: ").strip()
        except Cancelled:
            print("\nGoodbye.")
            return
        if choice == "1":
            run_find_replace_flow(directory)
        elif choice == "2":
            print("\nGoodbye.")
            return
        else:
            print("\nInvalid choice.")
        clear_line()


if __name__ == "__main__":
    try:
        main()
    except Cancelled:
        print("\nCancelled by user.")
        sys.exit(1)
    except Exception as exc:
        print(f"\nUnexpected error: {exc}")
        sys.exit(1)
