import json
import sys

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evaluation.frontiermemory_topic import summarize  # noqa: E402


def _turn(turn_id, user, work):
    return {
        "turn_id": turn_id,
        "user_id": user,
        "conversation_id": f"c-{user}",
        "source_task": "task",
        "gold_work": work,
        "messages": [{"role": "user", "message_id": turn_id, "content": f"Request {turn_id}"}],
    }


MANIFEST = {
    "turns": [
        _turn("a1", "u1", "alpha"),
        _turn("a2", "u2", "alpha"),
        _turn("b1", "u1", "beta"),
        _turn("b2", "u2", "beta"),
    ]
}


def _state(memberships):
    topics = sorted({topic for ids in memberships.values() for topic in ids})
    return {
        "turns": [
            {
                "turn_id": turn_id,
                "topic_ids": ids,
                "witness_topic_ids": [],
                "status": "assigned" if ids else "unassigned",
            }
            for turn_id, ids in memberships.items()
        ],
        "topics": [{"topic_id": topic, "name": topic} for topic in topics],
    }


def _write_run(root, name, live, flushed, **replay_extra):
    run = root / name
    run.mkdir()
    (run / "replay.json").write_text(json.dumps({**_state(live), **replay_extra}))
    (run / "flushed.json").write_text(json.dumps(_state(flushed)))
    return run


def test_run_metrics_score_the_flushed_state_and_keep_the_live_rate(tmp_path):
    run = _write_run(
        tmp_path,
        "head-1",
        live={"a1": ["t1"], "a2": [], "b1": [], "b2": []},
        flushed={"a1": ["t1"], "a2": ["t1"], "b1": ["t2"], "b2": ["t2"]},
        memos_commit="60d18117abcdef",
        budget={"estimated_usd": 1.5},
    )
    row = summarize.run_metrics(MANIFEST, run)
    assert row["memos_commit"] == "60d18117"
    assert row["allow_split_or_merge"] == 1.0 and row["strict_one_to_one"] == 1.0
    assert row["live_allow_split_or_merge"] == 0.5
    assert row["pair_precision"] == 1.0 and row["pair_recall"] == 1.0
    assert row["shapes"] == {"one_to_one": 2}
    assert row["estimated_usd"] == 1.5 and "reviewed" not in row


def test_summarize_groups_numbered_repeats_and_renders_one_row_per_run(tmp_path):
    good = {"a1": ["t1"], "a2": ["t1"], "b1": ["t2"], "b2": ["t2"]}
    merged = {"a1": ["t1"], "a2": ["t1"], "b1": ["t1"], "b2": ["t1"]}
    runs = [
        _write_run(tmp_path, "head-1", good, good),
        _write_run(tmp_path, "head-2", merged, merged),
    ]
    (runs[1] / "review-flushed.json").write_text(
        json.dumps(
            {
                "reviewer_model": "judge",
                "allow_split_or_merge_reviewed": {"correct": 0, "total": 2, "rate": 0.0},
            }
        )
    )
    report = summarize.summarize(MANIFEST, runs)
    group = report["groups"]["head"]
    assert group["runs"] == 2
    assert group["strict_one_to_one"] == {"mean": 0.5, "min": 0.0, "max": 1.0}
    assert group["allow_split_or_merge"]["mean"] == 1.0
    assert group["reviewed"] == {"mean": 0.0, "min": 0.0, "max": 0.0}
    table = summarize.markdown(report).splitlines()
    assert len(table) == 4 and table[1].startswith("|---|")
    assert table[3].startswith("| head-2 |") and "| 0/2/0/0/0 |" in table[3]
