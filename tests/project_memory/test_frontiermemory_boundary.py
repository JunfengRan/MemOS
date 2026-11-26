import sys

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from evaluation.frontiermemory_topic.boundary import boundary_metrics  # noqa: E402


def _manifest(*labels):
    return {
        "turns": [
            {"turn_id": tid, "conversation_id": conv, "gold_work": work}
            for tid, conv, work in labels
        ]
    }


def test_switches_are_measured_per_conversation_in_arrival_order():
    manifest = _manifest(
        ("a1", "c1", "export"),
        ("b1", "c2", "tax"),
        ("a2", "c1", "export"),
        ("a3", "c1", "import"),
        ("b2", "c2", "tax"),
    )
    replay = {
        "turns": [
            {"turn_id": "a1", "episode_id": "e1", "topic_ids": ["t1"]},
            {"turn_id": "a2", "episode_id": "e1", "topic_ids": ["t1"]},
            {"turn_id": "a3", "episode_id": "e1", "topic_ids": ["t1"]},
            {"turn_id": "b1", "episode_id": "e2", "topic_ids": ["t2"]},
            {"turn_id": "b2", "episode_id": "e3", "topic_ids": ["t2"]},
        ]
    }
    metrics = boundary_metrics(manifest, replay)
    assert metrics["gold_switches"] == 1
    assert metrics["switches_cut"] == 0 and metrics["switches_carried"] == 1
    assert metrics["multi_turn_episodes"] == 1 and metrics["mixed_episodes"] == 1


def test_a_cut_switch_in_its_own_topic_is_clean():
    manifest = _manifest(("a1", "c1", "export"), ("a2", "c1", "import"))
    replay = {
        "turns": [
            {"turn_id": "a1", "episode_id": "e1", "topic_ids": ["t1"]},
            {"turn_id": "a2", "episode_id": "e2", "topic_ids": ["t2"]},
        ]
    }
    metrics = boundary_metrics(manifest, replay)
    assert metrics["switch_recall"] == 1.0 and metrics["carried_share"] == 0.0
    assert metrics["mixed_episodes"] == 0
