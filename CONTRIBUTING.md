# Contributing to checkup

Thank you for your interest in contributing! This document explains how to get
involved — whether it's fixing a bug, proposing a feature, or improving the docs.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Features](#suggesting-features)
  - [Submitting Pull Requests](#submitting-pull-requests)
- [Development Setup](#development-setup)
- [Style Guide](#style-guide)
- [Project Scope](#project-scope)

---

## Code of Conduct

Be respectful and constructive. We welcome contributors of all skill levels.

---

## How to Contribute

### Reporting Bugs

1. Search existing [Issues](../../issues) to avoid duplicates.
2. Open a new issue and include:
   - OS and distro version (`uname -a`, `cat /etc/os-release`)
   - Python/Bash version (`python3 --version`, `bash --version`)
   - The exact command you ran
   - The full output or error message
   - What you expected vs. what happened

### Suggesting Features

Open an issue with the `enhancement` label.  
Describe the use case — what problem does this solve and who benefits?  
Keep the zero-dependency constraint in mind (see [Project Scope](#project-scope)).

### Submitting Pull Requests

1. **Fork** the repository and create a branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```

2. **Make your changes** — keep commits focused and the diff minimal.

3. **Test manually** on a real Linux system:
   ```bash
   # Quick smoke test — ping for 10 seconds, expect clean output
   ./checkup.py 127.0.0.1 --interval 1
   ./checkup.sh 127.0.0.1 --interval 1

   # Test flags
   ./checkup.py 8.8.8.8 --interval 1 --log /tmp/test.log --json-report /tmp/test.json
   ./checkup.py 8.8.8.8 --no-color --quiet
   ./checkup.py --help
   ./checkup.sh --help
   ```

4. **Update the README** if you add or change any CLI flags or behavior.

5. **Open a PR** against `main` with a clear description of:
   - What the change does
   - Why it is needed
   - How you tested it

---

## Development Setup

No build system or virtual environment needed — the tools are self-contained scripts.

```bash
git clone https://github.com/your-username/checkup.git
cd checkup
chmod +x checkup.py checkup.sh

# Verify Python version (3.6+ required)
python3 --version

# Verify Bash version (4+ required)
bash --version

# Verify ping is available
which ping
```

### Linting (optional but appreciated)

```bash
# Python — style check
python3 -m py_compile checkup.py && echo "Syntax OK"

# Bash — static analysis (install shellcheck if available)
shellcheck checkup.sh
```

---

## Style Guide

### Python (`checkup.py`)

- Follow [PEP 8](https://pep8.org/).
- Use type hints on all public method signatures.
- No external imports — standard library only.
- Keep classes and functions focused on a single responsibility.
- Prefer explicit over clever.

### Bash (`checkup.sh`)

- `set -euo pipefail` at the top (already enforced).
- Quote all variables: `"$VAR"` not `$VAR`.
- Use `[[ … ]]` for conditionals (not `[ … ]`).
- Prefer `local` variables inside functions.
- Run new code through `shellcheck` before submitting.

---

## Project Scope

**checkup is deliberately minimal.** Before adding a feature, ask:

| Question | If "no", reconsider |
|---|---|
| Does it work without any `pip install`? | Required |
| Does it work on a fresh Linux server with just `ping` and Python 3? | Required |
| Does it keep the script under ~300 lines? | Strongly preferred |
| Does it solve a common real-world outage-tracking need? | Expected |

Features we will **not** accept:

- External HTTP checks (use `curl`/`wget` separately)
- Email/Slack/webhook alerting hooks (out of scope — pipe to another tool)
- Dependency on third-party Python packages
- Windows-only or macOS-only features (Linux-first project)

---

Thank you for helping make **checkup** better!
