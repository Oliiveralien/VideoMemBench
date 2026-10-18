from __future__ import annotations

import json
import re

from videomembench.llm import LLMConfig, chat
from videomembench.dialogue import TF, turn_type
from inference.prompts import OPEN_JUDGE_SYSTEM

CHOICE_KEYS = ("A", "B", "C", "D", "E", "F", "G", "H")
_LETTER_RE = re.compile(r"\b([ABCDEFGH])\b", re.IGNORECASE)
_BOXED_LETTER_RE = re.compile(r"\\boxed\{\s*([A-Ha-h])\s*\}")
_BOXED_ANY_RE = re.compile(r"\\boxed\s*\{([^{}]*)\}")


def parse_choice(pred: str) -> tuple[str | None, str]:
    s = (pred or "").strip()
    m = _BOXED_LETTER_RE.search(s)
    if m:
        return m.group(1).upper(), "boxed"
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            obj = obj.get("answer") or obj.get("pred") or obj.get("choice")
        if isinstance(obj, list) and len(obj) == 1:
            obj = obj[0]
        if isinstance(obj, str) and obj.strip().upper() in CHOICE_KEYS:
            return obj.strip().upper(), "json"
    except Exception:
        pass
    m = re.fullmatch(r"[\"']\s*([A-Ha-h])\s*[\"']", s)
    if m:
        return m.group(1).upper(), "quoted_letter"
    if s.upper() in CHOICE_KEYS:
        return s.upper(), "bare_letter"
    m = _LETTER_RE.search(s)
    if m:
        return m.group(1).upper(), "regex_letter"
    return None, "unparsed"


def gold_answers(turn: dict) -> list[str]:
    golds: list[str] = []
    for x in turn.get("acceptable_answers") or []:
        if isinstance(x, str) and x.strip():
            golds.append(x.strip())
    for key in ("reference_answer", "answer"):
        v = turn.get(key)
        if isinstance(v, str) and v.strip():
            golds.append(v.strip())
    return list(dict.fromkeys(golds))


def true_false_rule(turn: dict, golds: list[str], pred: str) -> int | None:
    if turn_type(turn) != TF or not golds:
        return None
    g = golds[0].strip().lower()
    gold_bool = True if g in ("true", "yes", "t", "y") else (False if g in ("false", "no", "f", "n") else None)
    boxed = _BOXED_ANY_RE.findall(pred or "")
    segment = (boxed[-1] if boxed else (pred or "")[-200:]).lower()
    tokens = re.findall(r"\b(true|false|yes|no)\b", segment)
    if gold_bool is None or not tokens:
        return None
    return int((tokens[-1] in ("true", "yes")) == gold_bool)


def judge_open(judge: LLMConfig, question: str, golds: list[str], pred: str, *, attempts: int = 3) -> tuple[int, str | None]:
    payload = json.dumps({"question": question, "gold_answers": golds, "model_output": pred or ""}, ensure_ascii=False)
    err = None
    for _ in range(max(1, attempts)):
        try:
            raw = chat(judge, [{"role": "user", "content": payload}], system=OPEN_JUDGE_SYSTEM,
                       temperature=0.0, max_tokens=256, json_mode=True)
        except Exception as e:
            err = f"{type(e).__name__}: {str(e)[:200]}"
            continue
        try:
            obj = json.loads(raw)
            value = obj["correct"]
            score = obj["score"]
            if type(value) in (int, bool) and value in (0, 1) and type(score) in (int, bool) and score == value:
                return int(value), None
        except (ValueError, KeyError, TypeError):
            pass
        err = "judge returned an invalid binary JSON object"
    return 0, err
