# Evaluation Protocol

## Visual Input

The main evaluation uses 128 uniformly sampled frames over the full video.
For a video with N frames, the K sample indices are:

```text
index[i] = round(i * (N - 1) / (K - 1)),  i = 0, …, K - 1
```

Each frame is paired with its temporal position, computed as `index / FPS`.
Timestamp text uses `<MM:SS>` or `<HH:MM:SS>`; the cache retains exact seconds.
Frames are resized to a maximum side length of 512 pixels and encoded as JPEG
at quality 75. When N < K, indices repeat to retain the requested frame budget.
Invalid FPS or a decode failure stops preparation.

Prepare the frame cache once and share it across models. Each manifest records
the video checksum, sampling algorithm, frame indices, timestamps, and JPEG
checksums. Inference verifies the cached images before evaluation. Decoding may
vary across video backends, so comparisons should reuse cached images rather
than regenerate frames separately for each model.

## Conversation History

The frame sequence is included at the start of the first user message and remains
in the conversation history throughout the dialogue. Later user messages contain
the current question and answer options where applicable.

At turn t, the input is:

```text
V || (q_1, a_hat_1) || … || (q_{t-1}, a_hat_{t-1}) || q_t
```

Here V is the timestamped frame sequence and a_hat_i is the model's full response
at turn i. Questions follow annotation order, and history resets between videos.
Gold answers, correctness labels, dependency fields, and evidence windows are
not included in model inputs. No audio or subtitles are used.

Decoding defaults are temperature 0 and a maximum of 2048 output tokens. Endpoints
must preserve all frames and the complete history without truncation.

## Response Grading

**Multiple choice.** Extract an A–H option in the following order: boxed letter,
JSON answer, quoted letter, bare letter, then the first standalone letter token.
Compare the extracted key with the reference option. Unparsed or out-of-option
responses receive 0. Each result stores `parse_method` for inspection.

**Open answers.** GPT-5.4 mini grades semantic equivalence between the response and
any acceptable reference answer. The grader receives the question, references,
and full response. It returns JSON with matching binary `score` and `correct`
fields. Malformed grades are retried. A different judge constitutes a separate
evaluation setting.

**True/false.** Option-based questions use MC extraction. Without options, the
last recognized true/false/yes/no token is compared against a boolean reference;
other responses use the open-answer grader.

## Metrics

Let c(t) be binary response correctness, T all turns, E turns with at least one
Episodic parent, A turns with at least one Answer parent, and Anc_ans(t) all
ancestors reachable by recursively following Answer edges toward earlier turns.

```text
TurnAcc   = 100 × sum(c(t) for t in T) / |T|
EpiDepAcc = 100 × sum(c(t) for t in E) / |E|
AnsDepAcc = 100 × sum(c(t) × product(c(a) for a in Anc_ans(t)) for t in A) / |A|
Overall   = (TurnAcc + EpiDepAcc + AnsDepAcc) / 3
```

Episodic edges are excluded from Answer-ancestor traversal at every depth.
EpiDepAcc does not require correct parent answers. Mixed-dependency turns appear
in both dependency subsets under their respective rules.

Metrics pool turns across all videos rather than averaging video-level scores.
Overall is an equal mean over overlapping subsets. Empty subsets are `null`
(`N/A` in Markdown); Overall is undefined if any constituent is undefined.
Supplementary JSON fields include IndepAcc, accuracy over turns without parents,
and Dep, the mean of EpiDepAcc and AnsDepAcc.

## Run Management

A failed model call or unresolved grade aborts the current dialogue attempt.
Resumption retries failed dialogues from their start and skips completed videos.
The run manifest checks the model ID, judge ID, annotations, cached frames, token
limit, and additional request settings. Keep endpoint deployments fixed, and use
a new output path when changing weights or server settings.

Use one writer per output file. Invalid JSONL records must be repaired before
resuming. The scorer uses the latest attempt for each video and rejects incomplete
runs by default. `--allow-incomplete` is for diagnostics only: all annotated turns
remain in the denominator and missing turns count as incorrect.

## Frame-Count Ablations

For 16-, 32-, or 64-frame evaluation, prepare a separate cache with `--frames K`
and use the same frame budget during inference. Report the frame budget alongside
results. The main evaluation uses 128 frames.
