"""
Tests for remove (rm) operations in cpbar.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

import os
import sys
import tempfile
from io import StringIO
import shutil
from pathlib import Path
import pytest

from cpbar.operations import get_all_files, do_remove
from cpbar.ui import getch


class TestRemoveOperations:
    """Test suite for remove operations."""

    def setup_method(self):
        """Setup test fixtures before each test."""
        self.test_dir = tempfile.mkdtemp()
        self.work_dir = Path(self.test_dir)

    def teardown_method(self):
        """Cleanup after each test."""
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_files_for_removal_single(self):
        """Test getting a single file for removal."""
        test_file = self.work_dir / "file.txt"
        test_file.write_text("content")

        files = get_all_files([str(test_file)], recursive=False)
        
        assert len(files) == 1
        assert files[0][0] == str(test_file)

    def test_get_files_for_removal_directory_recursive(self):
        """Test getting files from a directory recursively for removal."""
        # Create test structure
        (self.work_dir / "file1.txt").write_text("a")
        (self.work_dir / "file2.txt").write_text("bb")
        subdir = self.work_dir / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("ccc")

        files = get_all_files([str(self.work_dir)], recursive=True)
        
        assert len(files) == 3

    def test_remove_empty_directory_requires_recursive(self):
        """Test that removing a directory without -r flag should fail."""
        import sys
        from io import StringIO

        test_dir = self.work_dir / "emptydir"
        test_dir.mkdir()

        old_stderr = sys.stderr
        sys.stderr = StringIO()

        files = get_all_files([str(test_dir)], recursive=False)

        error_output = sys.stderr.getvalue()
        sys.stderr = old_stderr

        assert len(files) == 0
        assert "is a directory" in error_output

    def test_remove_symlink_removes_link_not_target(self):
        """Test that os.remove on a symlink removes the link, not the target file."""
        target = self.work_dir / "target.txt"
        target.write_text("target content")
        link = self.work_dir / "link.txt"
        link.symlink_to(target)

        assert link.is_symlink()

        # os.remove should remove the link, leaving target intact
        os.remove(str(link))

        assert not link.exists()
        assert target.exists()
        assert target.read_text() == "target content"

    def _remove_quiet(self, *args, **kwargs):
        """Run do_remove suppressing stdout (progress bar output)."""
        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            return do_remove(*args, **kwargs)
        finally:
            sys.stdout = old_stdout

    def test_remove_force_ignores_missing_files(self):
        """Test that rm -f on a missing path succeeds silently, like rm -f."""
        missing = self.work_dir / "missing.txt"

        old_stderr = sys.stderr
        sys.stderr = StringIO()
        try:
            self._remove_quiet([str(missing)], recursive=True, force=True)
            error_output = sys.stderr.getvalue()
        finally:
            sys.stderr = old_stderr

        assert error_output == ""

    def test_remove_without_force_fails_on_missing_files(self):
        """Test that rm without -f still fails on a missing path."""
        missing = self.work_dir / "missing.txt"

        old_stderr = sys.stderr
        sys.stderr = StringIO()
        try:
            with pytest.raises(SystemExit) as exc_info:
                self._remove_quiet([str(missing)], recursive=False, force=False)
        finally:
            sys.stderr = old_stderr

        assert exc_info.value.code == 1

    def test_remove_recursive_symlink_to_dir_removes_only_link(self):
        """Test that rm -rf on a symlink to a directory removes the link, never the target's contents."""
        target = self.work_dir / "real"
        (target / "sub").mkdir(parents=True)
        (target / "sub" / "keep.txt").write_text("keep me")
        link = self.work_dir / "link"
        link.symlink_to(target)

        self._remove_quiet([str(link)], recursive=True, force=True)

        assert not link.is_symlink()
        assert (target / "sub" / "keep.txt").read_text() == "keep me"

    def test_remove_broken_symlink(self):
        """Test that a dangling symlink can be removed."""
        link = self.work_dir / "dangling"
        link.symlink_to(self.work_dir / "nowhere")

        self._remove_quiet([str(link)], recursive=False, force=True)

        assert not link.is_symlink()


class TestGetchWithoutTerminal:
    """Test suite for prompts when stdin is not a terminal."""

    def test_getch_eof_answers_no(self, monkeypatch):
        """Test that running out of input answers 'n' instead of crashing."""
        monkeypatch.setattr("sys.stdin", StringIO(""))

        assert getch("yn") == "n"

    def test_remove_confirmation_eof_cancels(self, monkeypatch, tmp_path):
        """Test that rm without -f and no input cancels instead of deleting."""
        target = tmp_path / "file.txt"
        target.write_text("content")
        monkeypatch.setattr("sys.stdin", StringIO(""))
        monkeypatch.setattr("cpbar.operations.time.sleep", lambda seconds: None)

        old_stdout = sys.stdout
        sys.stdout = StringIO()
        try:
            with pytest.raises(SystemExit) as exc_info:
                do_remove([str(target)], recursive=False, force=False)
        finally:
            sys.stdout = old_stdout

        assert exc_info.value.code == 0
        assert target.exists()
