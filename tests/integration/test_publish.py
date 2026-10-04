import subprocess

import pytest

from ffforecast.publish import PublishError, publish_site


def make_remote(tmp_path):
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "gh-pages", str(remote)], check=True)
    return remote


def commit_count(remote):
    out = subprocess.run(
        ["git", "--git-dir", str(remote), "rev-list", "--count", "gh-pages"],
        capture_output=True,
        text=True,
        check=True,
    )
    return int(out.stdout)


def test_publish_replaces_history_with_one_commit(tmp_path):
    remote = make_remote(tmp_path)
    site = tmp_path / "site"
    site.mkdir()
    for n in range(3):
        (site / "index.html").write_text(f"<html>run {n}</html>")
        publish_site(site, str(remote), message=f"run {n}")
    assert commit_count(remote) == 1  # history never grows
    shown = subprocess.run(
        ["git", "--git-dir", str(remote), "show", "gh-pages:index.html"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "run 2" in shown.stdout
    names = subprocess.run(
        ["git", "--git-dir", str(remote), "ls-tree", "--name-only", "gh-pages"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert ".nojekyll" in names


def test_publish_refuses_empty_site(tmp_path):
    with pytest.raises(PublishError, match="index.html"):
        publish_site(tmp_path, str(make_remote(tmp_path)))


def test_publish_failure_is_reported(tmp_path):
    site = tmp_path / "s"
    site.mkdir()
    (site / "index.html").write_text("x")
    with pytest.raises(PublishError, match="push"):
        publish_site(site, str(tmp_path / "no-such-remote"))
