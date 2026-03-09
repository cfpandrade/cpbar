# Contributing to cpbar

Thank you for your interest in contributing to cpbar! This document provides guidelines and instructions for contributing.

## Code of Conduct

Be respectful, constructive, and professional. We welcome contributions from everyone.

## How to Contribute

### Reporting Bugs

Before creating a bug report, please check existing issues to avoid duplicates.

**Good bug reports include:**
- Clear, descriptive title
- Steps to reproduce the issue
- Expected vs. actual behavior
- Environment details (OS, Python version, cpbar version)
- Relevant code snippets or error messages

**Example:**
```markdown
**Bug:** Progress bar doesn't work in tmux

**Environment:**
- OS: Ubuntu 22.04
- Python: 3.10
- cpbar: 1.5.0
- Shell: bash in tmux 3.2

**Steps to reproduce:**
1. Start tmux session
2. Run `cpbar cp large_file.iso /backup/`
3. Progress bar appears broken

**Expected:** Smooth progress bar
**Actual:** Garbled output with escape codes
```

### Suggesting Features

Feature suggestions are welcome! Open an issue with:
- Clear description of the feature
- Use case / problem it solves
- Example of how it would work
- Any potential implementation ideas

### Pull Requests

1. **Fork the repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/cpbar.git
   cd cpbar
   ```

2. **Create a branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/issue-123
   ```

3. **Set up development environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements-dev.txt
   ```

4. **Make your changes**
   - Write clean, readable code
   - Follow existing code style
   - Add tests for new features
   - Update documentation as needed

5. **Run tests**
   ```bash
   pytest tests/ -v
   pytest tests/ --cov=cpbar  # With coverage
   ```

6. **Run code quality checks**
   ```bash
   ruff check cpbar/
   ruff format cpbar/  # Auto-format code
   ```

7. **Commit your changes**
   ```bash
   git add .
   git commit -m "Add feature: parallel delete mode"
   ```

   **Commit message guidelines:**
   - Use present tense ("Add feature" not "Added feature")
   - Be descriptive but concise
   - Reference issues: "Fix #123: Handle symlinks correctly"
   - Group related changes in one commit

8. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```
   Then open a Pull Request on GitHub.

**Good PRs include:**
- Clear description of what changed and why
- Link to related issues
- Screenshots/examples for UI changes
- Updated tests
- Updated documentation

## Development Guidelines

### Code Style

- Follow PEP 8
- Use type hints where beneficial
- Keep functions focused and concise
- Add docstrings to public functions
- Use meaningful variable names

**Example:**
```python
def copy_file_with_progress(
    src: str,
    dst: str,
    progress: ProgressBar,
    buffer_size: int = BUFFER_SIZE
) -> bool:
    """Copy a single file with progress updates.
    
    Args:
        src: Source file path
        dst: Destination file path
        progress: ProgressBar instance for tracking
        buffer_size: Read buffer size in bytes (default: 16MB)
    
    Returns:
        True if successful, False if skipped by user
    """
    # Implementation...
```

### Testing

- Write tests for new features
- Update tests when changing existing features
- Aim for >80% code coverage
- Test edge cases (empty files, large files, permissions, etc.)
- Test on multiple Python versions if possible

**Test structure:**
```python
class TestFeatureName:
    """Test suite for feature X."""
    
    def setup_method(self):
        """Setup before each test."""
        # Create temporary files, etc.
    
    def teardown_method(self):
        """Cleanup after each test."""
        # Remove temporary files
    
    def test_basic_case(self):
        """Test the basic use case."""
        # Arrange
        # Act
        # Assert
    
    def test_edge_case(self):
        """Test edge case Y."""
        # ...
```

### Documentation

Update documentation when:
- Adding new features
- Changing behavior
- Fixing bugs that weren't intuitive

Documentation locations:
- **README.md**: User-facing documentation, usage examples
- **Docstrings**: For developers, API documentation
- **ARCHITECTURE.md**: Design decisions, how things work
- **CHANGELOG.md**: User-facing changes per version

## Project Structure

```
cpbar/
├── cpbar/              # Main package
│   ├── __init__.py     # Package initialization, version
│   ├── core.py         # CLI argument parsing, main entry
│   ├── operations.py   # File operations (copy, remove)
│   ├── ui.py           # Progress bar, colors, TTY handling
│   ├── utils.py        # Helper functions, config
│   └── benchmark.py    # Parallel mode benchmarking
├── tests/              # Test suite
│   ├── test_copy.py
│   ├── test_remove.py
│   └── ...
├── .github/
│   └── workflows/
│       └── ci.yml      # GitHub Actions CI
├── README.md
├── CONTRIBUTING.md     # This file
├── PUBLISHING.md       # Release guide
├── ARCHITECTURE.md     # Design documentation
├── pyproject.toml      # Modern Python packaging
└── requirements-dev.txt
```

## Development Workflow

### Running Tests Locally

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_copy.py -v

# Run specific test
pytest tests/test_copy.py::TestCopyOperations::test_copy_single_file -v

# Run with coverage
pytest tests/ --cov=cpbar --cov-report=html
# Open htmlcov/index.html in browser
```

### Testing Different Scenarios

```bash
# Test TTY mode (normal terminal)
python -m cpbar cp test.txt dest.txt

# Test non-TTY mode (pipe)
python -m cpbar cp test.txt dest.txt | cat

# Test dry-run
python -m cpbar cp -n large_folder/ /backup/

# Test parallel mode
python -m cpbar cp -P large_file.iso /backup/
```

### Debugging

```python
# Add debug output
import sys
print(f"DEBUG: variable={value}", file=sys.stderr)

# Use pdb for interactive debugging
import pdb; pdb.set_trace()
```

## Getting Help

- Check existing issues and documentation
- Open a new issue for questions
- Tag your issue appropriately (question, bug, feature, etc.)

## Recognition

Contributors will be recognized in:
- GitHub contributors list
- Release notes for significant contributions
- Special thanks in README for major features

Thank you for contributing to cpbar! 🙏
