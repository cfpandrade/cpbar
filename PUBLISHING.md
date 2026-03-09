# Publishing Guide for cpbar

This guide explains how to publish cpbar to PyPI.

## Prerequisites

1. Install build tools:
```bash
pip install build twine
```

2. Create accounts on:
- PyPI: https://pypi.org/account/register/
- TestPyPI (for testing): https://test.pypi.org/account/register/

3. Configure API tokens:
```bash
# Create ~/.pypirc
[distutils]
index-servers =
    pypi
    testpypi

[pypi]
username = __token__
password = pypi-...  # Your PyPI API token

[testpypi]
username = __token__
password = pypi-...  # Your TestPyPI API token
```

## Publishing Steps

### 1. Update Version

Edit `cpbar/__init__.py` and update `__version__`:

```python
__version__ = "1.6.0"  # Bump version
```

Also update version in `pyproject.toml`.

### 2. Update Changelog

Add release notes to README.md or CHANGELOG.md documenting new features, bug fixes, and breaking changes.

### 3. Create Git Tag

```bash
git add cpbar/__init__.py pyproject.toml
git commit -m "Bump version to 1.6.0"
git tag -a v1.6.0 -m "Release v1.6.0"
git push origin master --tags
```

### 4. Build Distribution

```bash
# Clean previous builds
rm -rf dist/ build/ *.egg-info

# Build
python -m build
```

This creates:
- `dist/cpbar-1.6.0-py3-none-any.whl` (wheel)
- `dist/cpbar-1.6.0.tar.gz` (source distribution)

### 5. Test on TestPyPI (Optional but Recommended)

```bash
# Upload to TestPyPI
python -m twine upload --repository testpypi dist/*

# Test installation
pip install --index-url https://test.pypi.org/simple/ --no-deps cpbar
cpbar --version
```

### 6. Publish to PyPI

```bash
python -m twine upload dist/*
```

### 7. Verify Installation

```bash
# In a fresh virtualenv or environment
pip install cpbar
cpbar --version
cpbar --help
```

## Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** version (X.0.0): Incompatible API changes
- **MINOR** version (0.X.0): Add functionality in backwards-compatible manner
- **PATCH** version (0.0.X): Backwards-compatible bug fixes

Examples:
- Bug fix: 1.5.0 → 1.5.1
- New feature: 1.5.1 → 1.6.0
- Breaking change: 1.6.0 → 2.0.0

## Release Checklist

- [ ] All tests passing (`pytest`)
- [ ] CI is green
- [ ] Version bumped in `__init__.py` and `pyproject.toml`
- [ ] Changelog updated
- [ ] Git tag created
- [ ] Built successfully (`python -m build`)
- [ ] Tested on TestPyPI (optional)
- [ ] Published to PyPI
- [ ] Installation verified
- [ ] GitHub Release created with notes

## Troubleshooting

### "File already exists"

You can't re-upload the same version. Bump the version number.

### Import errors after installation

Make sure all dependencies are listed in `pyproject.toml` and that the package structure is correct.

### Missing files in distribution

Check `MANIFEST.in` and ensure all necessary files are included.

## Automation (Future)

Consider setting up GitHub Actions to:
- Automatically build and publish on tagged releases
- Run tests before publishing
- Generate changelog from commit messages
