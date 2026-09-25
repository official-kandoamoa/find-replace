**AI development disclosure:** This project was developed with assistance from the free versions of ChatGPT, Grok, and Claude (LLMs), with the user providing ideas and testing while the AIs and user collaboratively suggested, generated, reviewed, and refined code and solutions.

# Find & Replace CLI

**100% Python** · Dependency-free · Termux / Android compatible

A lightweight, dependency-free command-line find-and-replace tool written entirely in Python.

Search and replace text in a single file or across an entire directory with a safe workflow:

**Scan → Preview → Confirm → Backup → Replace → Verify**

The tool supports literal searches, case-insensitive searches, and regular expressions. It also automatically skips common binary, generated, temporary, and dependency directories.

## Features

* 🔎 Find and replace text across files
* 📄 Process a specific file
* 📁 Process all files in the current directory
* 📂 Optionally scan subdirectories recursively
* 🔤 Literal search mode
* 🔡 Case-insensitive search mode
* 🧩 Regular expression support
* 👀 Preview changes before modifying files
* ✅ Ask for confirmation before applying changes
* 💾 Optional automatic backups
* 🔍 Verify files after writing
* 🚫 Automatically skip binary and unwanted files
* 🛑 Safe cancellation with `Ctrl+C` / `Ctrl+D`
* 📱 Works with Termux / Android
* 📦 No third-party Python dependencies

## Requirements

* Python 3.9 or newer
* No external Python packages are required.

## Installation

```bash
git clone https://github.com/official-kandoamoa/find-replace.git
cd find-replace
python find_replace.py
```

Or install it as a Python CLI package:

```bash
python -m pip install .
find-replace
```

## Command-Line Usage

Interactive mode:

```bash
python find_replace.py
```

Basic find and replace:

```bash
python find_replace.py --find "hello" --replace "world"
```

Replace in a specific file:

```bash
python find_replace.py \
    --file example.txt \
    --find "hello" \
    --replace "world"
```

Replace with an empty string:

```bash
python find_replace.py --find "DELETE_ME"
```

The interactive workflow is:

```text
Input → Scan → Preview → Confirm → Backup → Replace → Verify → Summary
```

## Search Modes

* **Literal** — searches for the exact text.
* **Case-insensitive** — matches different capitalization.
* **Regular expression** — uses Python regular expressions.

## Files That Are Skipped

The tool skips common binary, generated, temporary, and dependency files and directories, including `.git`, `__pycache__`, `node_modules`, `.venv`, images, archives, databases, and compiled files.

Files containing a NUL byte in their first 8192 bytes are also treated as probably binary.

## Supported Encodings

The tool attempts UTF-8, UTF-8 with BOM, and Latin-1, in that order. Files that cannot be decoded are skipped.

## Backups and Verification

Backups are enabled by default after confirmation. Existing backups are never overwritten; additional names such as `example.txt.bak1` are used. After writing, the file is read again and checked against the expected content.

## Termux Usage

```bash
termux-setup-storage
cd ~/storage/shared/Documents
python find_replace.py
```

## Project Structure

```text
find-replace/
├── find_replace.py   # Python CLI application
├── pyproject.toml    # Python project metadata
├── .gitattributes    # Marks the project as Python for GitHub Linguist
├── README.md
└── LICENSE
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

## Contributing

Contributions and improvements are welcome. Please test literal, case-insensitive, regex, single-file, recursive, backup, cancellation, and error-handling behavior when submitting changes.
