"""Command line interface (see specs/001-free-flying-forecast/contracts/cli.md)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from . import ausrasp, schedule
from .config import ConfigError, load_rules, load_site
from .models import Forecast
from .pipeline import run_pipeline
from .render import render_to_dir
from .runner import RunConfig, gfs_stages, make_finder
from .state import State

DEFAULT_SITE = Path("config/site.mystic.toml")
DEFAULT_RULES = Path("config/rules.toml")


def _load_config(args: argparse.Namespace):
    return load_site(Path(args.site)), load_rules(Path(args.rules))


def cmd_check(args: argparse.Namespace) -> int:
    try:
        site, rules = _load_config(args)
    except ConfigError as e:
        print(f"invalid config: {e}", file=sys.stderr)
        return 1
    print(f"ok: site '{site.id}', rules v{rules.version} ({rules.source})")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    try:
        site, rules = _load_config(args)
        fc = Forecast.from_dict(json.loads(Path(args.input).read_text()))
    except (ConfigError, OSError, KeyError, json.JSONDecodeError) as e:
        print(f"cannot render: {e}", file=sys.stderr)
        return 1
    path = render_to_dir(fc, site, rules, Path(args.out))
    print(f"wrote {path} ({path.stat().st_size} bytes)")
    return 0


def _run_config(args: argparse.Namespace, site, rules) -> RunConfig:
    return RunConfig(
        site=site,
        rules=rules,
        cache_dir=Path(args.cache),
        publish_remote=args.publish_remote,
        publish_branch=args.publish_branch,
        publish_key=Path(args.publish_key) if args.publish_key else None,
    )


def cmd_run(args: argparse.Namespace) -> int:
    import requests

    try:
        site, rules = _load_config(args)
    except ConfigError as e:
        print(f"invalid config: {e}", file=sys.stderr)
        return 1
    if args.model != "gfs":
        print(
            "--model wrf needs the WRF container on the iMac and is not wired up yet "
            "(see specs/001-free-flying-forecast/tasks.md, phase 4). Use --model gfs.",
            file=sys.stderr,
        )
        return 3
    cfg = _run_config(args, site, rules)
    session = requests.Session()
    state = State(Path(args.state))
    with state.lock():
        code, rec = run_pipeline(
            make_finder(cfg, session),
            lambda cycle: gfs_stages(cfg, cycle, session),
            state,
            Path(args.out),
            Path(args.work),
            retries=args.retries,
            retry_sleep_s=args.retry_sleep,
            force=args.force,
        )
    print(f"{rec.outcome}: cycle {rec.cycle or '-'} in {rec.duration_s}s")
    if rec.outcome in ("published", "skipped_duplicate"):
        # Each GFS cycle is about 400 MB, twice a day: keep only the newest two cycles.
        state.prune_runs(Path(args.cache) / "gfs", keep=2)
    return code


def cmd_poll(args: argparse.Namespace) -> int:
    """Check AUSRASP for changed days; if any were stored, rebuild the page once (spec 003)."""
    import requests

    try:
        site, rules = _load_config(args)
    except ConfigError as e:
        print(f"invalid config: {e}", file=sys.stderr)
        return 1
    a = site.ausrasp
    if not a.enabled:
        print("poll: AUSRASP is turned off in the site configuration")
        return 0
    store = ausrasp.store_dir(Path(args.cache))
    now = datetime.now(UTC)
    last = ausrasp.parse_iso(ausrasp.read_status(store).get("last_check"))
    if args.if_due and not schedule.due(now, last, a.windows, a.default_every_min):
        print("poll: not due")
        return 0
    session = requests.Session()
    result = ausrasp.refresh(a, site, Path(args.cache), session)
    if result.reason:
        print(f"poll: AUSRASP unavailable ({result.reason}); the page keeps its current figures")
        return 0
    if not result.changed:
        print("poll: no change")
        return 0
    msg = f"poll: {len(result.changed)} changed ({', '.join(result.changed)})"
    state = State(Path(args.state))
    cycle = state.last_published_cycle()
    if args.no_rebuild or cycle is None:
        print(msg + ("" if args.no_rebuild else "; no published run to rebuild"))
        return 0
    cfg = _run_config(args, site, rules)
    with state.lock(wait=False) as free:
        if not free:
            print(msg + "; a run is in progress and will pick the new values up")
            return 0
        code, rec = run_pipeline(
            lambda: cycle,
            lambda c: gfs_stages(cfg, c, session, refresh_ausrasp=False),
            state,
            Path(args.out),
            Path(args.work),
            retries=0,
            force=True,
        )
    print(f"{msg}; rebuild {rec.outcome} in {rec.duration_s}s")
    return code


def cmd_not_ready(args: argparse.Namespace) -> int:
    print(
        f"'{args.command}' needs the WRF container on the iMac and is not wired up yet "
        "(see specs/001-free-flying-forecast/tasks.md, phase 4).",
        file=sys.stderr,
    )
    return 3


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ffforecast")
    p.add_argument("--site", default=str(DEFAULT_SITE))
    p.add_argument("--rules", default=str(DEFAULT_RULES))
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="validate config files").set_defaults(func=cmd_check)
    r = sub.add_parser("render", help="render the static page from forecast.json")
    r.add_argument("--input", default="out/forecast.json")
    r.add_argument("--out", default="out")
    r.set_defaults(func=cmd_render)

    def run_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--cache", default="cache")
        p.add_argument("--state", default="state")
        p.add_argument("--out", default="out")
        p.add_argument("--work", default="work")
        p.add_argument("--publish-remote", default=None, help="git remote URL for static hosting")
        p.add_argument("--publish-branch", default="gh-pages")
        p.add_argument("--publish-key", default=None, help="path to an SSH deploy key")

    run = sub.add_parser("run", help="fetch, build the forecast, render and optionally publish")
    run.add_argument("--model", choices=("gfs", "wrf"), default="gfs")
    run.add_argument("--force", action="store_true", help="run even if the cycle is published")
    run.add_argument("--retries", type=int, default=6, help="retries when data is late")
    run.add_argument("--retry-sleep", type=float, default=600, help="seconds between retries")
    run_args(run)
    run.set_defaults(func=cmd_run)
    poll = sub.add_parser(
        "poll", help="check AUSRASP for new thermal data and rebuild the page if it changed"
    )
    poll.add_argument("--if-due", action="store_true", help="do nothing unless a check is due")
    poll.add_argument("--no-rebuild", action="store_true", help="store new data, do not rebuild")
    run_args(poll)
    poll.set_defaults(func=cmd_poll)
    for name in ("fetch", "wrf", "diagnose", "publish"):
        sub.add_parser(name).set_defaults(func=cmd_not_ready)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
