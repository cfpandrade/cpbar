"""
Tests for --verify (checksum verification) functionality in cpbar.

Author: Carlos Andrade <carlos@perezandrade.com>
"""

import hashlib
import io
import sys
import tempfile
import shutil
from pathlib import Path
import pytest

from cpbar.operations import copy_file_with_progress, do_copy
from cpbar.utils import compute_checksum
from cpbar.ui import ProgressBar


class TestComputeChecksum:
    """Test suite for compute_checksum utility."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()

    def teardown_method(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_checksum_known_value(self):
        """Test that compute_checksum matches hashlib reference for known content."""
        f = Path(self.test_dir) / "known.txt"
        content = b"hello cpbar"
        f.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        assert compute_checksum(str(f)) == expected

    def test_checksum_empty_file(self):
        """Test checksum of an empty file."""
        f = Path(self.test_dir) / "empty.txt"
        f.touch()

        expected = hashlib.sha256(b"").hexdigest()
        assert compute_checksum(str(f)) == expected

    def test_checksum_different_files_differ(self):
        """Test that different content produces different checksums."""
        f1 = Path(self.test_dir) / "a.txt"
        f2 = Path(self.test_dir) / "b.txt"
        f1.write_bytes(b"content A")
        f2.write_bytes(b"content B")

        assert compute_checksum(str(f1)) != compute_checksum(str(f2))

    def test_checksum_identical_files_match(self):
        """Test that identical content produces matching checksums."""
        f1 = Path(self.test_dir) / "a.txt"
        f2 = Path(self.test_dir) / "b.txt"
        f1.write_bytes(b"same content")
        f2.write_bytes(b"same content")

        assert compute_checksum(str(f1)) == compute_checksum(str(f2))


class TestVerifyCopy:
    """Test suite for --verify flag in copy operations."""

    def setup_method(self):
        self.test_dir = tempfile.mkdtemp()
        self.src_dir = Path(self.test_dir) / "src"
        self.dst_dir = Path(self.test_dir) / "dst"
        self.src_dir.mkdir()
        self.dst_dir.mkdir()

    def teardown_method(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_verify_clean_copy_passes(self):
        """Test that --verify passes when the copy is correct."""
        src = self.src_dir / "file.txt"
        src.write_bytes(b"clean content for verification")
        dst = self.dst_dir / "file.txt"

        progress = ProgressBar(total_items=1, total_bytes=src.stat().st_size, operation="cp")
        result = copy_file_with_progress(str(src), str(dst), progress, verify=True)
        progress.finish()

        assert result is True
        assert dst.read_bytes() == src.read_bytes()

    def test_verify_detects_corruption(self):
        """Test that --verify returns False when destination is corrupted."""
        src = self.src_dir / "file.txt"
        src.write_bytes(b"original content")
        dst = self.dst_dir / "file.txt"

        # Copy without verify first
        progress = ProgressBar(total_items=1, total_bytes=src.stat().st_size, operation="cp")
        copy_file_with_progress(str(src), str(dst), progress)
        progress.finish()

        # Corrupt the destination
        dst.write_bytes(b"corrupted content!")

        # Now run verify manually
        from cpbar.operations import verify_copy
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            result = verify_copy(str(src), str(dst))
            err_output = sys.stderr.getvalue()
        finally:
            sys.stderr = old_stderr

        assert result is False
        assert "FAILED" in err_output

    def test_verify_reports_to_stderr(self):
        """Test that verification failure message goes to stderr."""
        src = self.src_dir / "file.txt"
        src.write_bytes(b"data A")
        dst = self.dst_dir / "file.txt"
        dst.write_bytes(b"data B")

        from cpbar.operations import verify_copy
        old_stderr = sys.stderr
        sys.stderr = io.StringIO()
        try:
            verify_copy(str(src), str(dst))
            err_output = sys.stderr.getvalue()
        finally:
            sys.stderr = old_stderr

        assert "Verification FAILED" in err_output
        assert str(src) in err_output

    def test_do_copy_verify_exits_nonzero_on_mismatch(self, monkeypatch):
        """Test that do_copy with --verify exits with code 1 when verification fails."""
        src = self.src_dir / "file.txt"
        src.write_bytes(b"source content")

        # Monkeypatch verify_copy to always fail
        monkeypatch.setattr("cpbar.operations.verify_copy", lambda s, d, progress=None: False)

        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()
        try:
            with pytest.raises(SystemExit) as exc_info:
                do_copy([str(src)], str(self.dst_dir), recursive=False, verify=True)
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        assert exc_info.value.code == 1

    def test_do_copy_verify_success_prints_ok(self):
        """Test that do_copy with --verify prints 'all files OK' on success."""
        src = self.src_dir / "file.txt"
        src.write_bytes(b"good content")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            do_copy([str(src)], str(self.dst_dir), recursive=False, verify=True)
            output = sys.stdout.getvalue()
        finally:
            sys.stdout = old_stdout

        assert "all files OK" in output

    def test_do_copy_verify_skipped_file_is_not_a_failure(self, monkeypatch):
        """Test that declining an overwrite with --verify does not count as a verification failure."""
        src = self.src_dir / "file.txt"
        src.write_bytes(b"new content")
        (self.dst_dir / "file.txt").write_bytes(b"old content")

        monkeypatch.setattr("cpbar.ui.getch", lambda valid_keys: "n")

        old_stdout = sys.stdout
        sys.stdout = io.StringIO()
        try:
            do_copy([str(src)], str(self.dst_dir), recursive=False, verify=True)
        finally:
            sys.stdout = old_stdout

        assert (self.dst_dir / "file.txt").read_bytes() == b"old content"
