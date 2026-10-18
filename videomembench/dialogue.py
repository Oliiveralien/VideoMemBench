from __future__ import annotations

MCQ = "multi_choice_question"
TF = "true_or_false_question"
OPEN = "open_structured"

ANSWER = "answer"
EPISODIC = "episodic"
_DEP_ALIASES = {"answer": ANSWER, "episodic": EPISODIC, "referent": EPISODIC}

_TYPE_ALIASES = {
    "mcq": MCQ, "multiple choice": MCQ, "multiple-choice": MCQ, "multi_choice": MCQ, "multi-choice": MCQ,
    "tf": TF, "true/false": TF, "true_or_false": TF, "true or false": TF,
    "open-structured": OPEN, "open": OPEN,
}


def turn_type(turn: dict) -> str:
    t = str(turn.get("type") or "").strip()
    return _TYPE_ALIASES.get(t.lower(), t)


def parents(turn: dict) -> dict[str, str]:
    dep = turn.get("dependency")
    if not isinstance(dep, dict):
        return {}
    dep_type = dep.get("dep_type") if isinstance(dep.get("dep_type"), dict) else {}
    out = {}
    for pid in dep.get("depends_on") or list(dep_type):
        kind = _DEP_ALIASES.get(str(dep_type.get(pid, "")).strip().lower())
        if kind:
            out[str(pid)] = kind
    return out


def answer_parents(turn: dict) -> list[str]:
    return [p for p, k in parents(turn).items() if k == ANSWER]


def episodic_parents(turn: dict) -> list[str]:
    return [p for p, k in parents(turn).items() if k == EPISODIC]


def answer_ancestors(dialogue: list[dict], turn_id: str) -> set[str]:
    by_id = {str(t.get("turn_id")): t for t in dialogue}
    seen: set[str] = set()
    stack = answer_parents(by_id[turn_id]) if turn_id in by_id else []
    while stack:
        p = stack.pop()
        if p in seen or p not in by_id:
            continue
        seen.add(p)
        stack.extend(answer_parents(by_id[p]))
    return seen
