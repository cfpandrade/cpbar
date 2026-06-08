"""
Tests for move operations in cpbar.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

import io
import os
import sys
import tempfile
import shutil
from pathlib import Path
import pytest

from cpbar.operations import do_move


class TestMoveOperations:
    """Test suite for move operations."""

    def setup_method(self):
        """Setup test fixtures before each test."""
        self.test_dir = tempfile.mkdtemp()
        self.src_dir = Path(self.test_dir) / "src"
        self.dst_dir = Path(self.test_dir) / "dst"
        self.src_dir.mkdir()
        self.dst_dir.mkdir()

    def teardown_method(self):
        """Cleanup after each test."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _suppress_output(self, func, *args, **kwargs):
        """Run func suppressing stdout (progress bar output)."""
        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            return func(*args, **kwargs)
        finally:
            sys.stdout = old_stdout

    def test_move_file_same_filesystem(self):
        """Test moving a file on the same filesystem."""
        src_file = self.src_dir / "file.txt"
        content = "Hello, move!"
        src_file.write_text(content)

        self._suppress_output(do_move, [str(src_file)], str(self.dst_dir), recursive=False)

        assert not src_file.exists()
        dst_file = self.dst_dir / "file.txt"
        assert dst_file.exists()
        assert dst_file.read_text() == content

    def test_move_renames_on_same_fs(self, monkeypatch):
        """Test that same-filesystem moves use rename (not copy+delete)."""
        src_file = self.src_dir / "file.txt"
        src_file.write_text("content")

        rename_called = [False]
        original_rename = Path.rename

        def tracked_rename(self_path, target):
            rename_called[0] = True
            return original_rename(self_path, target)

        monkeypatch.setattr(Path, 'rename', tracked_rename)

        self._suppress_output(do_move, [str(src_file)], str(self.dst_dir), recursive=False)

        assert rename_called[0], "rename() should have been called for same-fs move"
        assert not src_file.exists()
        assert (self.dst_dir / "file.txt").exists()

    def test_move_cross_filesystem_fallback(self, monkeypatch):
        """Test that cross-filesystem moves fall back to copy+delete."""
        src_file = self.src_dir / "file.txt"
        content = b"cross-fs content"
        src_file.write_bytes(content)

        def failing_rename(self_path, target):
            raise OSError("Cross-device link")

        monkeypatch.setattr(Path, 'rename', failing_rename)

        self._suppress_output(do_move, [str(src_file)], str(self.dst_dir), recursive=False)

        assert not src_file.exists(), "Source should be deleted after cross-fs move"
        dst_file = self.dst_dir / "file.txt"
        assert dst_file.exists()
        assert dst_file.read_bytes() == content

    def test_move_file_into_directory(self):
        """Test moving a file into an existing directory."""
        src_file = self.src_dir / "myfile.txt"
        src_file.write_text("data")

        self._suppress_output(do_move, [str(src_file)], str(self.dst_dir), recursive=False)

        assert not src_file.exists()
        assert (self.dst_dir / "myfile.txt").read_text() == "data"

    def test_move_directory_recursive(self):
        """Test moving a directory with nested structure."""
        src_subdir = self.src_dir / "nested"
        src_subdir.mkdir()
        (self.src_dir / "a.txt").write_text("aaa")
        (src_subdir / "b.txt").write_text("bbb")

        new_dst = Path(self.test_dir) / "new_dst"
        new_dst.mkdir()

        self._suppress_output(do_move, [str(self.src_dir)], str(new_dst), recursive=True)

        # Files should be at new_dst/src/a.txt and new_dst/src/nested/b.txt
        assert (new_dst / "src" / "a.txt").read_text() == "aaa"
        assert (new_dst / "src" / "nested" / "b.txt").read_text() == "bbb"
        # Source files should be gone
        assert not (self.src_dir / "a.txt").exists()
        assert not (src_subdir / "b.txt").exists()

    def test_move_dry_run(self):
        """Test that dry-run mode does not actually move files."""
        src_file = self.src_dir / "file.txt"
        src_file.write_text("content")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            do_move([str(src_file)], str(self.dst_dir), recursive=False, dry_run=True)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert src_file.exists(), "Source should still exist after dry-run"
        assert not (self.dst_dir / "file.txt").exists(), "Destination should not exist after dry-run"
        assert "Dry-run" in output

    def test_move_no_sources_exits(self):
        """Test that empty source list causes sys.exit."""
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            with pytest.raises(SystemExit):
                do_move([], str(self.dst_dir), recursive=False)
        finally:
            sys.stderr = old_stderr

    def test_move_nonexistent_source(self):
        """Test that all-nonexistent sources causes sys.exit."""
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            with pytest.raises(SystemExit):
                do_move(["/nonexistent/path/file.txt"], str(self.dst_dir), recursive=False)
        finally:
            sys.stderr = old_stderr

    # --- Symlink tests ---

    def test_move_symlink_same_fs_renames_link(self, monkeypatch):
        """Test that moving a symlink on same-fs renames the link itself, not the target."""
        target = self.src_dir / "target.txt"
        target.write_text("target content")
        link = self.src_dir / "link.txt"
        link.symlink_to(target)

        original_rename = Path.rename
        renamed_paths = []

        def tracked_rename(self_path, tgt):
            renamed_paths.append(str(self_path))
            return original_rename(self_path, tgt)

        monkeypatch.setattr(Path, 'rename', tracked_rename)

        self._suppress_output(do_move, [str(link)], str(self.dst_dir), recursive=False)

        # The link should have been moved (renamed), not the target
        dst_link = self.dst_dir / "link.txt"
        assert dst_link.is_symlink(), "Moved entry should be a symlink (rename preserves it)"
        assert target.exists(), "Original target should be untouched"
        assert not link.exists(), "Original link should be gone"
