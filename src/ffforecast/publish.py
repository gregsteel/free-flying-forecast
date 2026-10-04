"""Publish the rendered site to a git remote (GitHub Pages) as a single orphan commit."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path


class PublishError(RuntimeError):
    pass


def _git(args: list[str], cwd: Path, env: dict[str, str]) -> None:
    r = subprocess.run(["git", *args], cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise PublishError(f"git {' '.join(args)} failed: {r.stderr.strip() or r.stdout.strip()}")


def publish_site(
    site_dir: Path,
    remote: str,
    branch: str = "gh-pages",
    key_path: Path | None = None,
    message: str = "Publish forecast",
) -> None:
    """Force-push `site_dir` to `remote` as one fresh commit so history never grows."""
    if not (site_dir / "index.html").exists():
        raise PublishError(f"{site_dir} has no index.html; nothing to publish")
    env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "Free Flying Forecast",
        "GIT_AUTHOR_EMAIL": "ffforecast@localhost",
        "GIT_COMMITTER_NAME": "Free Flying Forecast",
        "GIT_COMMITTER_EMAIL": "ffforecast@localhost",
        "GIT_TERMINAL_PROMPT": "0",
    }
    if key_path is not None:
        env["GIT_SSH_COMMAND"] = (
            f"ssh -i {key_path} -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new"
        )
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "site"
        shutil.copytree(site_dir, work)
        (work / ".nojekyll").write_text("")
        _git(["init", "-q", "-b", branch], work, env)
        _git(["add", "-A"], work, env)
        _git(["commit", "-q", "-m", message], work, env)
        _git(["push", "-q", "--force", remote, f"{branch}:{branch}"], work, env)
