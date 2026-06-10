"""Optional Phase-8 charts (factor tornado + score heatmap) as PNGs.

Imported lazily by the CLI only when ``--charts`` is passed, so matplotlib stays
an *optional* dependency (``pip install -e .[viz]``). Every function degrades to
a no-op list if matplotlib is missing.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def _matplotlib():
    import matplotlib
    matplotlib.use("Agg")          # headless / CI-safe
    import matplotlib.pyplot as plt
    return plt


def render_tornado(result: dict[str, Any], path: Path) -> Path:
    plt = _matplotlib()
    ensemble = result["ensemble"]
    eff = {s["name"]: s.get("effective_weight", 0.0)
           for s in ensemble.breakdown_payload.get("signals", [])}
    rows = []
    for s in result["signals"]:
        if not s.available:
            continue
        impact = eff.get(s.name, 0.0) * (s.home_strength - s.away_strength)
        if abs(impact) < 1e-6:
            continue
        rows.append((s.name, impact))
    rows.sort(key=lambda r: abs(r[1]))
    names = [r[0] for r in rows]
    vals = [r[1] for r in rows]
    colors = ["#2e7d32" if v >= 0 else "#c62828" for v in vals]

    fig, ax = plt.subplots(figsize=(8, max(3, 0.4 * len(names) + 1)))
    ax.barh(names, vals, color=colors)
    ax.axvline(0, color="#333", lw=0.8)
    ax.set_xlabel("← away favour      weighted Δ(home − away)      home favour →")
    ax.set_title("Factor Tornado")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def render_heatmap(result: dict[str, Any], path: Path) -> Path:
    plt = _matplotlib()
    matrix = result.get("score_matrix") or []
    n = min(7, len(matrix))
    grid = [[matrix[i][j] for j in range(n)] for i in range(n)]
    cfg = result.get("config", {})
    teams = cfg.get("teams", {})
    home = (teams.get("home", {}) or {}).get("name", "Home")
    away = (teams.get("away", {}) or {}).get("name", "Away")

    fig, ax = plt.subplots(figsize=(6, 5))
    im = ax.imshow(grid, cmap="viridis", origin="upper")
    ax.set_xticks(range(n)); ax.set_yticks(range(n))
    ax.set_xlabel(f"{away} goals"); ax.set_ylabel(f"{home} goals")
    ax.set_title("Score Probability Matrix")
    for i in range(n):
        for j in range(n):
            ax.text(j, i, f"{100*grid[i][j]:.0f}", ha="center", va="center",
                    color="white" if grid[i][j] < (im.get_clim()[1] * 0.6) else "black",
                    fontsize=8)
    fig.colorbar(im, ax=ax, label="probability")
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


def render_charts(result: dict[str, Any], out_dir: Path, match_id: str) -> list[Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = [
        render_tornado(result, out_dir / f"{match_id}_tornado.png"),
        render_heatmap(result, out_dir / f"{match_id}_heatmap.png"),
    ]
    return written


__all__ = ["render_charts", "render_tornado", "render_heatmap"]
