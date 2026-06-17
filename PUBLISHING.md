# Publishing Guide

How to release a new version of checkup via both the install script and PyPI.

---

## Prerequisites

Install the build and publish tools once:

```bash
pip install --upgrade build twine
```

Create a PyPI account at https://pypi.org and generate an API token:
- Account Settings → API tokens → Add API token (scope: entire account)
- Save the token somewhere safe (you only see it once)

Configure credentials locally so twine can authenticate:

```bash
# ~/.pypirc
[pypi]
  username = __token__
  password = pypi-<your-token-here>
```

---

## Release checklist

### 1. Bump the version

Edit the version in **two places**:

| File | What to change |
|------|---------------|
| `checkup.py` | `__version__ = "X.Y.Z"` (line 26) |
| `pyproject.toml` | `version = "X.Y.Z"` |

Follow [semver](https://semver.org/):
- `PATCH` (1.2.x) — bug fixes, no new features
- `MINOR` (1.x.0) — new features, backward compatible
- `MAJOR` (x.0.0) — breaking changes

### 2. Update README.md

- Update the version badge / version number in the header
- Add the new features/fixes to the **Changelog** section
- Update usage examples if the CLI changed

### 3. Commit and tag

```bash
git checkout dev
git add checkup.py pyproject.toml README.md
git commit -m "chore: bump version to X.Y.Z"
git push origin dev
```

Merge dev → main when ready to release:

```bash
git checkout main
git merge dev
git tag vX.Y.Z
git push origin main
git push origin vX.Y.Z
git checkout dev
git push origin dev
```

### 4. Build the package

```bash
# from the repo root
python3 -m build
```

This creates two files in `dist/`:
- `checkup-X.Y.Z.tar.gz` — source distribution
- `checkup-X.Y.Z-py3-none-any.whl` — wheel

### 5. Test locally before publishing

```bash
# install from the wheel into a temp venv to verify it works
python3 -m venv /tmp/checkup-test
/tmp/checkup-test/bin/pip install dist/checkup-X.Y.Z-py3-none-any.whl
/tmp/checkup-test/bin/checkup --version
/tmp/checkup-test/bin/checkup 8.8.8.8
```

### 6. Publish to PyPI

```bash
python3 -m twine upload dist/*
```

After upload, verify at: https://pypi.org/project/checkup/

### 7. Test the install script

```bash
curl -fsSL https://raw.githubusercontent.com/vgrigolaia/checkup/main/install.sh | bash
checkup --version
```

---

## User install methods

### One-line install (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/vgrigolaia/checkup/main/install.sh | bash
```

### pip / pipx

```bash
pip install checkup
# or (isolated, recommended for CLI tools)
pipx install checkup
```

### Uninstall

```bash
# if installed via install.sh
sudo rm /usr/local/bin/checkup

# if installed via pip
pip uninstall checkup

# if installed via pipx
pipx uninstall checkup
```

---

## Clean up dist/ before each release

```bash
rm -rf dist/ *.egg-info
```

Never commit the `dist/` directory — it is already in `.gitignore`.
