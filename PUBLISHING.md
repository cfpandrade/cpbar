# Publishing Guide for cpbar

This guide explains how to publish cpbar to PyPI using either automated workflows (recommended) or manual publishing.

## Method 1: Automated Publishing (Recommended)

The project uses GitHub Actions with **Trusted Publishers** for secure, automated PyPI publishing. No API tokens needed!

### First-Time Setup

#### 1. Configure PyPI Trusted Publisher

1. Go to https://pypi.org/manage/account/publishing/
2. Click "Add a new publisher"
3. Fill in the form:
   - **PyPI Project Name:** `cpbar`
   - **Owner:** `cfpandrade` (your GitHub username)
   - **Repository name:** `cpbar`
   - **Workflow name:** `publish-pypi.yml`
   - **Environment name:** `pypi` (optional but recommended)
4. Click "Add"

#### 2. Configure TestPyPI Trusted Publisher (Optional)

Same process at https://test.pypi.org/manage/account/publishing/
- Environment name: `testpypi`

### Publishing a New Release

1. **Update version** in `cpbar/__init__.py` and `pyproject.toml`:
   ```python
   __version__ = "1.6.0"
   ```

2. **Commit and tag:**
   ```bash
   git add cpbar/__init__.py pyproject.toml
   git commit -m "Bump version to 1.6.0"
   git tag -a v1.6.0 -m "Release v1.6.0"
   git push origin master --tags
   ```

3. **Create GitHub Release:**
   ```bash
   gh release create v1.6.0 \
     --title "cpbar v1.6.0" \
     --notes "## What's new
   
   - Feature X
   - Bug fix Y
   - Performance improvement Z
   
   See [CHANGELOG](CHANGELOG.md) for full details."
   ```
   
   Or use the GitHub web UI: https://github.com/cfpandrade/cpbar/releases/new

4. **Done!** 
   - GitHub Actions automatically builds and publishes to PyPI and TestPyPI
   - Monitor progress: https://github.com/cfpandrade/cpbar/actions

### Manual Trigger

You can also manually trigger the workflow without creating a release:

```bash
gh workflow run publish-pypi.yml
```

Or via the GitHub web UI: Actions → Publish to PyPI → Run workflow

---

## Method 2: Manual Publishing

If you prefer or need to publish manually:

### Prerequisites

1. Install build tools:
   ```bash
   pip install build twine
   ```

2. Create accounts:
   - PyPI: https://pypi.org/account/register/
   - TestPyPI (optional): https://test.pypi.org/account/register/

3. Create API tokens:
   - PyPI: https://pypi.org/manage/account/token/
   - TestPyPI: https://test.pypi.org/manage/account/token/

4. Configure `~/.pypirc`:
   ```ini
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

### Manual Publishing Steps

1. **Update version** (same as automated method)

2. **Clean and build:**
   ```bash
   rm -rf dist/ build/ *.egg-info
   python -m build
   ```

3. **Test on TestPyPI (optional):**
   ```bash
   python -m twine upload --repository testpypi dist/*
   
   # Test installation
   pip install --index-url https://test.pypi.org/simple/ --no-deps cpbar
   cpbar --version
   ```

4. **Publish to PyPI:**
   ```bash
   python -m twine upload dist/*
   ```

5. **Verify:**
   ```bash
   pip install cpbar
   cpbar --version
   ```

6. **Create Git tag and GitHub release** (same as automated method)

---

## Version Numbering

We follow [Semantic Versioning](https://semver.org/):

- **MAJOR** version (X.0.0): Incompatible API changes
- **MINOR** version (0.X.0): Add functionality in backwards-compatible manner
- **PATCH** version (0.0.X): Backwards-compatible bug fixes

Examples:
- Bug fix: 1.5.0 → 1.5.1
- New feature: 1.5.1 → 1.6.0
- Breaking change: 1.6.0 → 2.0.0

---

## Release Checklist

- [ ] All tests passing (`pytest`)
- [ ] CI is green (GitHub Actions)
- [ ] Version bumped in `cpbar/__init__.py` and `pyproject.toml`
- [ ] CHANGELOG updated (if using one)
- [ ] Committed and pushed to master
- [ ] Git tag created (`git tag -a vX.Y.Z -m "..."`)
- [ ] Tag pushed (`git push --tags`)
- [ ] GitHub Release created with release notes

**For automated publishing:**
- [ ] Trusted Publisher configured on PyPI (one-time)
- [ ] GitHub Release created → workflow runs automatically

**For manual publishing:**
- [ ] Built distribution (`python -m build`)
- [ ] Published to PyPI (`twine upload`)
- [ ] Installation verified

---

## Troubleshooting

### "Publishing is disabled for this project"

**Cause:** Trusted Publisher not configured on PyPI.

**Fix:** Go to https://pypi.org/manage/account/publishing/ and add the publisher (see First-Time Setup above).

### "Invalid or insufficient permissions"

**Cause:** GitHub Actions doesn't have permission to access PyPI.

**Fix:** 
1. Make sure `id-token: write` permission is in the workflow
2. Verify Trusted Publisher configuration matches exactly (repo name, owner, workflow name)

### "File already exists"

**Cause:** You can't re-upload the same version to PyPI.

**Fix:** Bump the version number.

### Workflow fails on TestPyPI but succeeds on PyPI

**Cause:** TestPyPI and PyPI are separate systems. If the version already exists on TestPyPI from a previous test, it will fail.

**Fix:** This is normal and OK. The PyPI publish (which matters) succeeded.

### Import errors after installation

**Cause:** Missing dependencies or incorrect package structure.

**Fix:** 
1. Check dependencies in `pyproject.toml`
2. Verify package structure with `python -m build` and inspect `dist/`
3. Test locally: `pip install dist/cpbar-*.whl`

---

## References

- [PyPI Trusted Publishers Guide](https://docs.pypi.org/trusted-publishers/)
- [Python Packaging Guide](https://packaging.python.org/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Semantic Versioning](https://semver.org/)
