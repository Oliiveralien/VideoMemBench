"""Validate VideoMemBench evaluation annotations."""
from __future__ import annotations
import argparse
import json
from .dialogue import MCQ, OPEN, TF, turn_type

ITEM_FIELDS = {"video_id", "video_name", "dialogue"}
TURN_FIELDS = {"turn_id", "type", "question", "options", "answer", "reference_answer",
               "acceptable_answers", "dependency", "evidence"}

def validate(items: list[dict]) -> None:
    if not items:
        raise ValueError("annotations must contain at least one video")
    videos, ids = set(), set()
    for item in items:
        if not isinstance(item, dict) or set(item) - ITEM_FIELDS:
            raise ValueError("use the evaluation schema only: video_id, video_name, dialogue")
        for key, seen in (("video_name", videos), ("video_id", ids)):
            value = item.get(key)
            if not isinstance(value, str) or not value.strip() or value in seen:
                raise ValueError(f"missing/duplicate {key}: {value!r}")
            seen.add(value)
        turns = item.get("dialogue")
        if not isinstance(turns, list) or not turns:
            raise ValueError("dialogue must be a nonempty list")
        previous = set()
        for t in turns:
            if not isinstance(t, dict) or set(t) - TURN_FIELDS:
                raise ValueError("unknown turn fields: export evaluation fields only")
            tid = t.get("turn_id")
            if not isinstance(tid, str) or not tid.strip() or tid in previous:
                raise ValueError(f"missing/duplicate turn_id: {tid!r}")
            if not isinstance(t.get("question"), str) or not t["question"].strip():
                raise ValueError(f"empty question at {tid}")
            typ = turn_type(t)
            if typ not in (MCQ, TF, OPEN):
                raise ValueError(f"unknown question type at {tid}")
            opts = t.get("options")
            if opts is not None and (not isinstance(opts, dict) or any(
                    k not in 'ABCDEFGH' or len(k) != 1 or not isinstance(v, str) or not v.strip()
                    for k, v in opts.items())):
                raise ValueError(f"invalid options at {tid}")
            if typ == MCQ and (not opts or len(opts) < 2):
                raise ValueError(f"multiple choice needs at least two options at {tid}")
            if opts and typ in (MCQ, TF):
                if t.get("answer") not in opts:
                    raise ValueError(f"answer must be an option key at {tid}")
            else:
                golds = [t.get("answer"), t.get("reference_answer")]
                accepted = t.get("acceptable_answers", [])
                if not isinstance(accepted, list) or any(not isinstance(g, str) or not g.strip() for g in accepted):
                    raise ValueError(f"acceptable_answers must be a list of nonempty strings at {tid}")
                if not any(isinstance(g, str) and g.strip() for g in golds + accepted):
                    raise ValueError(f"missing reference answer at {tid}")
            dep = t.get("dependency")
            if dep is not None:
                if not isinstance(dep, dict) or set(dep) != {"depends_on", "dep_type"}:
                    raise ValueError(f"invalid dependency at {tid}")
                ps, types = dep['depends_on'], dep['dep_type']
                if not isinstance(ps, list) or any(not isinstance(p, str) for p in ps) or len(set(ps)) != len(ps):
                    raise ValueError(f"invalid parents at {tid}")
                if not isinstance(types, dict) or set(types) != set(ps):
                    raise ValueError(f"parent/type mismatch at {tid}")
                if any(p not in previous for p in ps):
                    raise ValueError(f"parents must refer to earlier turns at {tid}")
                if any(k not in ('answer', 'episodic', 'referent') for k in types.values()):
                    raise ValueError(f"unknown dependency type at {tid}")
            previous.add(tid)

def load(path: str) -> list[dict]:
    with open(path, encoding='utf8') as f:
        items = [json.loads(line) for line in f if line.strip()]
    validate(items)
    return items

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('annotations')
    args = ap.parse_args()
    items = load(args.annotations)
    print(f"Valid: {len(items)} videos, {sum(len(i['dialogue']) for i in items)} turns")

if __name__ == '__main__':
    main()
