"""``wm2026`` command-line entry point.

    wm2026 predict --match config/matches/group_a/cze_vs_rsa.yaml
    wm2026 predict --home Germany --away Brazil --stage QF --odds "2.10/3.40/3.20"
    wm2026 list

``predict`` runs the full 8-phase pipeline and prints the Markdown report; with
``--out DIR`` it also writes ``<match_id>.json`` + ``<match_id>.md`` (and PNG
charts when ``--charts`` and matplotlib are available).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path


def _quiet_logs(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(message)s")
    try:
        import structlog

        structlog.configure(
            wrapper_class=structlog.make_filtering_bound_logger(level)
        )
    except Exception:
        pass


def _add_predict_args(p: argparse.ArgumentParser) -> None:
    src = p.add_argument_group("match input (use --match OR --home/--away)")
    src.add_argument("--match", "-m", help="path to a match config YAML")
    src.add_argument("--home", help="home team name (ad-hoc match)")
    src.add_argument("--away", help="away team name (ad-hoc match)")
    src.add_argument("--home-code", help="home FIFA code (default: first 3 letters)")
    src.add_argument("--away-code", help="away FIFA code")
    src.add_argument("--stage", default="Group", help="Group | R32 | R16 | QF | SF | Final")
    src.add_argument("--kickoff", help="ISO8601 kickoff, e.g. 2026-06-12T21:00:00Z")
    src.add_argument("--venue", help="stadium / city")
    src.add_argument("--home-xg", type=float, default=1.40)
    src.add_argument("--away-xg", type=float, default=1.30)
    src.add_argument("--home-xga", type=float, default=1.30)
    src.add_argument("--away-xga", type=float, default=1.40)
    src.add_argument("--home-elo", type=int, default=1700)
    src.add_argument("--away-elo", type=int, default=1700)

    odds = p.add_argument_group("odds (Phase 6 edge table)")
    odds.add_argument("--odds", help="1X2 decimal odds, e.g. \"2.10/3.40/3.20\"")
    odds.add_argument("--odds-ou", help="Over/Under 2.5 odds, e.g. \"1.85/1.95\"")
    odds.add_argument("--odds-btts", help="BTTS Yes/No odds, e.g. \"1.80/2.00\"")
    odds.add_argument("--odds-dc", help="Double Chance odds 1X/12/X2, e.g. \"1.25/1.30/1.55\"")
    odds.add_argument("--odds-ah", help="Asian-handicap line + home/away odds, "
                                        "\"LINE:HOME/AWAY\". Use = for negative lines, "
                                        "e.g. --odds-ah=-0.5:1.95/1.95")

    run = p.add_argument_group("run options")
    run.add_argument("--mode", choices=["mock", "live"], default="mock",
                     help="mock = offline/no keys (default); live = use .env toggles")
    run.add_argument("--bootstrap", type=int, default=None,
                     help="bootstrap samples for CIs (default: settings.bootstrap_n)")
    run.add_argument("--sentiment-json", help="path to a sentiment_payload JSON to inject")
    run.add_argument("--out", "-o", help="output directory for JSON/MD/PNG")
    run.add_argument("--json-only", action="store_true", help="print JSON instead of Markdown")
    run.add_argument("--charts", action="store_true", help="also render PNG charts (needs matplotlib)")
    run.add_argument("--verbose", "-v", action="store_true", help="show debug logs")


def _parse_ah(spec: str | None) -> tuple[float, float | None, float | None] | None:
    """Parse ``"LINE:HOME/AWAY"`` (e.g. ``"-0.5:1.95/1.95"``) into
    ``(line, home_odd, away_odd)``. Returns ``None`` for an empty/invalid spec."""
    if not spec:
        return None
    from wm2026.edge import parse_odds

    try:
        line_part, odds_part = spec.split(":", 1)
        line = float(line_part)
    except ValueError:
        return None
    odds = parse_odds(odds_part) or []
    home_odd = odds[0] if len(odds) > 0 else None
    away_odd = odds[1] if len(odds) > 1 else None
    return (line, home_odd, away_odd)


def _build_cfg(args: argparse.Namespace):
    from wm2026.context import load_match_config, synth_config

    if args.match:
        return load_match_config(args.match)
    if args.home and args.away:
        return synth_config(
            home_team=args.home, away_team=args.away,
            home_code=args.home_code, away_code=args.away_code,
            stage=args.stage, kickoff=args.kickoff, venue=args.venue,
            home_xg=args.home_xg, away_xg=args.away_xg,
            home_xga=args.home_xga, away_xga=args.away_xga,
            home_elo=args.home_elo, away_elo=args.away_elo,
            odds_1x2=args.odds,
        )
    raise SystemExit("error: provide --match <yaml> or both --home and --away")


def _cmd_predict(args: argparse.Namespace) -> int:
    _quiet_logs(args.verbose)
    # Pre-seed mock toggles before the heavy imports so even import-time settings
    # reflect the chosen profile (apply_runtime_profile re-asserts them anyway).
    if args.mode == "mock":
        for k in (
            "USE_MOCK_CRAWLER", "USE_MOCK_OPENFOOTBALL", "USE_MOCK_THESPORTSDB",
            "USE_MOCK_OPENLIGADB", "USE_MOCK_WIKIDATA", "USE_MOCK_WEATHER",
            "USE_MOCK_RSS", "USE_MOCK_CLUBELO", "USE_MOCK_FOOTBALL_DATA",
            "USE_MOCK_FBREF", "USE_MOCK_UNDERSTAT", "USE_MOCK_FOTMOB",
            "USE_MOCK_SOFASCORE", "USE_MOCK_TRANSFERMARKT",
        ):
            os.environ.setdefault(k, "true")

    from wm2026.edge import parse_odds
    from wm2026.pipeline import run_prediction
    from wm2026.report import build_report

    cfg = _build_cfg(args)
    sentiment = None
    if args.sentiment_json:
        sentiment = json.loads(Path(args.sentiment_json).read_text(encoding="utf-8"))

    result = asyncio.run(run_prediction(
        cfg,
        mode=args.mode,
        bootstrap_n=args.bootstrap,
        sentiment_payload=sentiment,
        odds_1x2=parse_odds(args.odds),
        odds_ou25=parse_odds(args.odds_ou),
        odds_btts=parse_odds(args.odds_btts),
        odds_dc=parse_odds(args.odds_dc),
        odds_ah=_parse_ah(args.odds_ah),
    ))
    report = build_report(result)

    if args.json_only:
        print(json.dumps(report["json"], indent=2, ensure_ascii=False))
    else:
        print(report["markdown"])

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        mid = report["json"]["match_id"]
        (out_dir / f"{mid}.json").write_text(
            json.dumps(report["json"], indent=2, ensure_ascii=False), encoding="utf-8")
        (out_dir / f"{mid}.md").write_text(report["markdown"], encoding="utf-8")
        written = [f"{mid}.json", f"{mid}.md"]
        if args.charts:
            try:
                from wm2026.viz import render_charts
                written += [p.name for p in render_charts(result, out_dir, mid)]
            except Exception as exc:
                print(f"[charts skipped: {exc}]", file=sys.stderr)
        print(f"\n→ wrote {', '.join(written)} to {out_dir}/", file=sys.stderr)
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    root = Path(args.dir or "config/matches")
    files = sorted(p for p in root.rglob("*.yaml") if not p.name.startswith("_"))
    if not files:
        print(f"no match configs under {root}/", file=sys.stderr)
        return 1
    for p in files:
        print(p)
    print(f"\n{len(files)} match configs", file=sys.stderr)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wm2026",
        description="WM 2026 — Match-Analyse & Prediction workflow (8-phase pipeline).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_predict = sub.add_parser("predict", help="run the full prediction pipeline")
    _add_predict_args(p_predict)
    p_predict.set_defaults(func=_cmd_predict)

    p_list = sub.add_parser("list", help="list available match configs")
    p_list.add_argument("--dir", help="match config root (default: config/matches)")
    p_list.set_defaults(func=_cmd_list)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
