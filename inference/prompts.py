EVAL_SYSTEM = (
    "You are an intelligent assistant.\n"
    "Answer the question concisely based on the video.\n"
)

CHOICE_ANSWER_INSTRUCTION = (
    "The final answer MUST BE put in \\boxed{}. "
    "For this multiple-choice question, put ONLY the option letter (e.g. A) inside the box."
)
OPEN_ANSWER_INSTRUCTION = "The final answer MUST BE put in \\boxed{}."


def choice_turn_text(question: str, options: dict, keys: tuple[str, ...]) -> str:
    opt_block = "\n".join(f"{k}. {str(options.get(k, '')).strip()}" for k in keys if k in options)
    return f"{question}\n" + (f"\n{opt_block}\n" if opt_block else "") + "\n" + CHOICE_ANSWER_INSTRUCTION


def open_turn_text(question: str) -> str:
    return question + "\n\n" + OPEN_ANSWER_INSTRUCTION


OPEN_JUDGE_SYSTEM = (
    "You are a strict semantic grader for open-ended answers.\n"
    "You will be given GOLD_ANSWERS and MODEL_OUTPUT.\n"
    "Judge whether MODEL_OUTPUT expresses the same meaning as any one of the GOLD_ANSWERS.\n"
    "Focus on semantic equivalence, not wording overlap.\n"
    "Partial answers, underspecified answers, or answers with conflicting key facts must receive a low score and correct=0.\n"
    "Ignore harmless extra wording only if the final answer meaning is still fully correct.\n"
    "Return a JSON object only with keys: score, correct, reason.\n"
    "Requirements:\n"
    "- score: either 0 or 1 (binary only, no fractional values)\n"
    "- correct: 1 only if MODEL_OUTPUT fully matches at least one gold answer in meaning, otherwise 0\n"
    "- score must always equal correct\n"
    "- reason: a short explanation that mentions the key match or mismatch\n"
    "You must always provide a numeric score.\n"
)
