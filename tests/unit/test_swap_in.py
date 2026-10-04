import errno
from pathlib import Path

import pytest

from ffforecast.pipeline import swap_in


def make(tmp_path: Path) -> tuple[Path, Path]:
    out = tmp_path / "out"
    out.mkdir()
    (out / "index.html").write_text("old")
    (out / "sub").mkdir()
    (out / "sub" / "x.txt").write_text("old x")
    staging = tmp_path / "work" / "staging"
    staging.mkdir(parents=True)
    (staging / "index.html").write_text("new")
    return out, staging


def test_swap_renames_and_keeps_the_previous_output(tmp_path):
    out, staging = make(tmp_path)
    swap_in(staging, out)
    assert (out / "index.html").read_text() == "new" and not (out / "sub").exists()
    assert (tmp_path / "out.prev" / "index.html").read_text() == "old"
    assert not staging.exists()


def test_swap_works_when_the_output_directory_cannot_be_renamed(tmp_path, monkeypatch):
    """A Docker volume mount point: renaming it fails with EBUSY, so the contents are copied."""
    out, staging = make(tmp_path)
    real = Path.rename

    def rename(self, target):
        if self == out:
            raise OSError(errno.EBUSY, "Device or resource busy")
        return real(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    swap_in(staging, out)
    assert (out / "index.html").read_text() == "new" and not (out / "sub").exists()
    assert (tmp_path / "out.prev" / "sub" / "x.txt").read_text() == "old x"
    assert not staging.exists()


def test_swap_works_when_staging_is_on_another_filesystem(tmp_path, monkeypatch):
    out, staging = make(tmp_path)
    real = Path.rename

    def rename(self, target):
        if self == staging:
            raise OSError(errno.EXDEV, "Invalid cross-device link")
        return real(self, target)

    monkeypatch.setattr(Path, "rename", rename)
    swap_in(staging, out)
    assert (out / "index.html").read_text() == "new"
    assert (tmp_path / "out.prev" / "index.html").read_text() == "old"
    assert not staging.exists()


def test_swap_into_a_missing_output_directory(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "index.html").write_text("new")
    swap_in(staging, tmp_path / "out")
    assert (tmp_path / "out" / "index.html").read_text() == "new"


@pytest.mark.parametrize("name", ["out"])
def test_a_failed_copy_does_not_hide_the_error(tmp_path, name):
    with pytest.raises(FileNotFoundError):
        swap_in(tmp_path / "missing-staging", tmp_path / name)
