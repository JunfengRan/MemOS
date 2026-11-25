"""Summarize replay run directories into one table per group of repeats.

Each run directory holds what ``run.sh`` writes: ``replay.json`` (live state after the last
wave), ``flushed.json`` (state after flush), optionally ``review-flushed.json``. Scores are
recomputed here from the manifest with the current ``score.py``, so runs made at different
times are compared under one scorer. Directories named ``<group>-<n>`` are grouped by
``<group>``.
"""

from __future__ import annotations

import argparse
import json
import re

from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

from .score import score_replay


_RULES = ("allow_split_or_merge", "strict_one_to_one", "allow_split", "allow_merge")
_SHAPES = ("one_to_one", "merge", "split", "mixed", "unassigned")


def _rate(row: dict[str, Any]) -> float | None:
    return row["rate"] if row["total"] else None


def run_metrics(manifest: dict[str, Any], run: Path) -> dict[str, Any]:
    """Score one run directory after flush (and live) and pick the reported metrics."""
    replay = json.loads((run / "replay.json").read_text(encoding="utf-8"))
    flushed_path = run / "flushed.json"
    flushed = (
        json.loads(flushed_path.read_text(encoding="utf-8")) if flushed_path.exists() else replay
    )
    score = score_replay(manifest, flushed)
    live = score_replay(manifest, replay)
    work = score["rubrics"]["gold_work"]
    attribution = work["task_topic_attribution"]
    by_conflict = attribution["by_conflict"]
    metrics: dict[str, Any] = {
        "run": run.name,
        "memos_commit": (replay.get("memos_commit") or "")[:8],
        "turns": score["turn_counts"]["total"],
        "assigned_turns": score["turn_counts"]["assigned"],
        "topics": len(flushed["topics"]),
        **{rule: _rate(attribution["rates"][rule]) for rule in _RULES},
        "live_allow_split_or_merge": _rate(
            live["rubrics"]["gold_work"]["task_topic_attribution"]["rates"]["allow_split_or_merge"]
        ),
        "with_conflict": _rate(by_conflict["with_conflict"]["rates"]["allow_split_or_merge"]),
        "without_conflict": _rate(by_conflict["without_conflict"]["rates"]["allow_split_or_merge"]),
        "pair_precision": work["precision"],
        "pair_recall": work["recall"],
        "pair_f1": work["f1"],
        "source_task_recall": score["rubrics"]["source_task"]["recall"],
        "shapes": dict(Counter(row["shape"] for row in attribution["tasks"].values())),
        "conflicts": {
            kind: f"{row['correct']}/{row['total']}"
            for kind, row in score["conflicts"]["summary"].items()
            if row["total"]
        },
        "seconds": replay.get("seconds"),
        "estimated_usd": (replay.get("budget") or {}).get("estimated_usd"),
    }
    review_path = run / "review-flushed.json"
    if review_path.exists():
        review = json.loads(review_path.read_text(encoding="utf-8"))
        metrics["reviewed"] = review["allow_split_or_merge_reviewed"]["rate"]
        metrics["reviewer_model"] = review.get("reviewer_model")
    return metrics


def group_name(run: str) -> str:
    return re.sub(r"-\d+$", "", run)


def summarize(manifest: dict[str, Any], runs: list[Path]) -> dict[str, Any]:
    rows = [run_metrics(manifest, run) for run in runs]
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[group_name(row["run"])].append(row)
    summary = {}
    for name, members in groups.items():
        numeric = {
            key
            for row in members
            for key, value in row.items()
            if isinstance(value, int | float) and not isinstance(value, bool)
        }
        summary[name] = {
            "runs": len(members),
            **{
                key: {
                    "mean": mean(values),
                    "min": min(values),
                    "max": max(values),
                }
                for key in sorted(numeric)
                if (values := [row[key] for row in members if row.get(key) is not None])
            },
        }
    return {"runs": rows, "groups": summary}


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{100 * value:.1f}"


def markdown(report: dict[str, Any]) -> str:
    """One row per run: the main rate first, then the stricter shapes and pair scores."""
    header = (
        "| run | commit | split-or-merge | 1:1 | 1:N | N:1 | reviewed | no-conflict works"
        " | conflict works | pair P / R / F1 | shapes 1:1/merge/split/mixed/none | conflicts | $ |"
    )
    lines = [header, "|" + "|".join("---" for _ in range(header.count("|") - 1)) + "|"]
    for row in report["runs"]:
        shapes = "/".join(str(row["shapes"].get(shape, 0)) for shape in _SHAPES)
        conflicts = ", ".join(f"{kind} {value}" for kind, value in row["conflicts"].items()) or "—"
        usd = row.get("estimated_usd")
        lines.append(
            f"| {row['run']} | {row['memos_commit']} | {_pct(row['allow_split_or_merge'])}"
            f" | {_pct(row['strict_one_to_one'])} | {_pct(row['allow_split'])}"
            f" | {_pct(row['allow_merge'])} | {_pct(row.get('reviewed'))}"
            f" | {_pct(row['without_conflict'])} | {_pct(row['with_conflict'])}"
            f" | {_pct(row['pair_precision'])} / {_pct(row['pair_recall'])}"
            f" / {_pct(row['pair_f1'])} | {shapes} | {conflicts}"
            f" | {'—' if usd is None else f'{usd:.2f}'} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="JSON summary path")
    parser.add_argument("--markdown", type=Path, help="Also write a Markdown table here")
    parser.add_argument("runs", type=Path, nargs="+")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    report = summarize(manifest, sorted(args.runs))
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.write_text(markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
