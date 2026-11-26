"""Measure Episode boundaries against the gold work labels of one replay.

Within a conversation, a gold switch is a Turn whose gold_work differs from the previous Turn
of the same conversation. Three numbers tell whether Add cut Episodes where the work changed:

- mixed Episodes: Episodes whose Turns belong to more than one gold_work (should be rare);
- switch recall: gold switches that start a new Episode;
- carried switches: gold switches whose Topic is the same as the previous Turn's Topic, i.e.
  the new work was attached to the old one (lower is better).
"""

from __future__ import annotations

import argparse
import json

from collections import defaultdict
from itertools import pairwise
from pathlib import Path
from typing import Any


def boundary_metrics(manifest: dict[str, Any], replay: dict[str, Any]) -> dict[str, Any]:
    gold = {turn["turn_id"]: turn for turn in manifest["turns"]}
    observed = {turn["turn_id"]: turn for turn in replay["turns"]}
    by_episode: dict[str, set[str]] = defaultdict(set)
    sizes: dict[str, int] = defaultdict(int)
    for turn_id, row in observed.items():
        if row.get("episode_id") and turn_id in gold:
            by_episode[row["episode_id"]].add(gold[turn_id]["gold_work"])
            sizes[row["episode_id"]] += 1
    conversations: dict[str, list[dict]] = defaultdict(list)
    for turn in manifest["turns"]:  # manifest order is arrival order
        conversations[turn["conversation_id"]].append(turn)
    switches = cut = carried = 0
    for turns in conversations.values():
        for before, after in pairwise(turns):
            if before["gold_work"] == after["gold_work"]:
                continue
            switches += 1
            left, right = observed.get(before["turn_id"], {}), observed.get(after["turn_id"], {})
            cut += left.get("episode_id") != right.get("episode_id")
            shared = set(left.get("topic_ids") or []) & set(right.get("topic_ids") or [])
            carried += bool(shared)
    multi = [eid for eid, size in sizes.items() if size > 1]
    mixed = [eid for eid in multi if len(by_episode[eid]) > 1]
    return {
        "episodes": len(sizes),
        "multi_turn_episodes": len(multi),
        "mixed_episodes": len(mixed),
        "mixed_share": len(mixed) / len(sizes) if sizes else None,
        "gold_switches": switches,
        "switches_cut": cut,
        "switch_recall": cut / switches if switches else None,
        "switches_carried": carried,
        "carried_share": carried / switches if switches else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("runs", type=Path, nargs="+", help="replay.json or flushed.json files")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    for path in args.runs:
        replay = json.loads(path.read_text(encoding="utf-8"))
        print(json.dumps({"run": str(path), **boundary_metrics(manifest, replay)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
