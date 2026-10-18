# Evaluation data contract

A [JSON Schema](../examples/annotation.schema.json) describes the canonical file shape;
the Python validator also checks graph and answer consistency.

Use UTF-8 JSONL with one video and its ordered dialogue per line. See the
[example annotations](../examples/annotations.jsonl). Validate before any model calls:

```bash
python -m videomembench.data data/annotations.jsonl
```

| Field | Required | Meaning |
|---|---|---|
| `video_id` | yes | Unique, nonempty video identifier |
| `video_name` | yes | Unique relative video filename, resolved inside `--video-root` |
| `dialogue` | yes | Nonempty list in the original turn order |
| `turn_id` | yes | Unique nonempty string within the dialogue |
| `type` | yes | `multi_choice_question`, `open_structured`, or legacy `true_or_false_question` |
| `question` | yes | User question, with no appended gold answer |
| `options` | MC required | Map from uppercase A–H to nonempty text; MC requires at least two |
| `answer` | MC required | Exact option key, or an open reference string |
| `reference_answer` | open alternative | An additional open reference string |
| `acceptable_answers` | optional | List of acceptable open reference strings |
| `dependency` | optional | `null` or `{"depends_on":["T1"],"dep_type":{"T1":"answer"}}` |
| `evidence` | optional | Original annotation metadata, never used to select frames or sent to the model |

Each open question must have at least one nonempty reference. Dependency types
are `answer` or `episodic`; legacy `referent` maps to `episodic`. Each parent
must precede its child. `depends_on` and `dep_type` must have identical parent
sets. A turn can have multiple parents and both dependency types.

The validator checks field names, option keys, reference answers, turn identifiers,
and dependency order. Unknown top-level or turn fields are rejected.

The inference model sees the video frames, timestamps, questions, answer options,
and its own preceding responses. Gold answers, dependency annotations, evidence,
and correctness labels are never included in its input. The separate open-answer
grader receives only the question, gold references, and the model response.

## Results

One append-only JSONL record per video attempt: `video_id`, `video_name`, `model`,
`judge_model`, `protocol`, `run_id`, `frame_cache_sha256`, `sampled_frames`, `ok`,
`per_turn`, and elapsed time. Each completed turn stores its original response,
binary `correct`, and scorer; choice turns also store `parsed` and `parse_method`.
Failed attempts store a sanitized exception class. The scorer uses the **latest
attempt per video**, rejects duplicates within a dialogue and mixed run IDs, and
reports counts and audit fields in JSON format. Incomplete results require the
explicit `--allow-incomplete` diagnostic flag.
