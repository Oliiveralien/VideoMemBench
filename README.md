<div align="center">
  <img src="assets/hero.svg" width="100%" alt="VideoMemBench — what a model has seen, what a model has said" />

# VideoMemBench
### How Well Do MLLMs Remember in Video Conversations?

**Zhengdong Hu\*** · **Chao Wang\*** · Kaituo Feng · Huanjin Yao · Mingfei Lu · Hehe Fan · Yi Yang†

<sub>University of Technology Sydney · The Chinese University of Hong Kong<br/>
The Hong Kong University of Science and Technology · Zhejiang University<br/>
*Equal contribution · †Corresponding author</sub>

<br/><br/>

![Evaluation only](https://img.shields.io/badge/release-evaluation_only-725AF2?style=flat-square)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)
![128 frames](https://img.shields.io/badge/protocol-128_frames-14B8A6?style=flat-square)
![Self rollout](https://img.shields.io/badge/history-self_rollout-F59E0B?style=flat-square)

[Overview](#overview) · [Evaluation](#evaluation) · [Protocol](docs/PROTOCOL.md) · [Data Format](docs/DATA_FORMAT.md) · [Results](#results) · [Citation](#citation)

</div>

---

## Overview

**VideoMemBench** evaluates in-context video memory in multi-turn video conversations.
Later questions depend on earlier turns through two types of links: **Episodic
Dependencies**, which revisit a previously discussed scene or entity, and **Answer
Dependencies**, which build on an earlier answer.

<table>
<tr><th>Videos</th><th>Dialogue Turns</th><th>Dependent Turns</th><th>Video Duration</th></tr>
<tr><td align="center">326</td><td align="center">2,476</td><td align="center">1,387</td><td align="center">≈154 hours</td></tr>
</table>

Each model receives the same **128 timestamped frames**. Questions are presented
in dialogue order, with the model's own previous responses retained in the history.

## Evaluation

### Installation

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Data

Place annotations and videos under `data/`:

```text
data/
├── annotations.jsonl
└── videos/
    └── <video_name>.mp4
```

See [Data Format](docs/DATA_FORMAT.md) for the annotation schema.

### Prepare frames

```bash
python -m videomembench.data data/annotations.jsonl
python -m videomembench.video \
  --annotations data/annotations.jsonl \
  --video-root data/videos \
  --frame-cache cache/f128
```

Reuse the same frame cache across all models. The cache records frame indices,
timestamps, and checksums to keep visual input fixed.

### Run inference

Set model and judge endpoints in [`configs/evaluation.toml`](configs/evaluation.toml).
The main evaluation uses **GPT-5.4 mini** for open-answer grading. Set the model ID
exposed by your endpoint and provide credentials through environment variables:

```bash
export VMB_API_KEY="your-model-api-key"
export VMB_JUDGE_API_KEY="your-judge-api-key"

python -m inference.evaluate --config configs/evaluation.toml
```

For unauthenticated local endpoints, leave the corresponding key variable unset.
The vision endpoint must support 128 images and the complete dialogue history.
Use `--workers N` to evaluate videos concurrently; turns within each video remain
sequential. Repeating a run skips completed videos and retries failed dialogues.
Use a new output path when changing the model or evaluation settings.

### Compute scores

```bash
python -m inference.metrics \
  --annotations data/annotations.jsonl runs/my-model/eval.jsonl

python -m inference.metrics \
  --annotations data/annotations.jsonl \
  --format json runs/my-model/eval.jsonl > runs/my-model/metrics.json
```

Reports are available in Markdown, JSON, and CSV. Incomplete runs are rejected by
default. `--allow-incomplete` reports diagnostic scores with missing turns counted
as incorrect.

## Metrics

| Metric | Evaluation subset | Scoring |
|---|---|---|
| **TurnAcc** | All turns | Per-turn correctness |
| **EpiDepAcc** | Turns with at least one Episodic parent | Per-turn correctness, independent of parent correctness |
| **AnsDepAcc** | Turns with at least one Answer parent | Correctness of the turn and all recursive Answer ancestors |
| **Overall** | Three metrics | (TurnAcc + EpiDepAcc + AnsDepAcc) / 3 |

Answer-ancestor traversal follows **Answer edges only**. Episodic edges are excluded
at every depth. A turn with both dependency types contributes to both subsets.
Scores are pooled across turns and reported as percentages.

See [Evaluation Protocol](docs/PROTOCOL.md) for frame sampling, response grading,
and metric definitions.

## Results

Selected results from Table 2. Model results use 128 frames and self-rollout.
The human baseline has no fixed frame budget. All scores are percentages.

| Model | TurnAcc | EpiDepAcc | AnsDepAcc | Overall |
|---|---:|---:|---:|---:|
| Human | 88.1 | 86.0 | 84.2 | 86.1 |
| Claude Opus 5 | 52.3 | 49.1 | 35.7 | 45.7 |
| Gemini 3.8 Flash | 50.4 | 46.6 | 30.3 | 42.4 |
| GPT-5.6-sol | 50.0 | 47.8 | 27.1 | 41.7 |
| Kimi K3 | 50.5 | 49.0 | 27.1 | 42.2 |
| Qwen3-VL-235B-A22B | 43.1 | 41.6 | 18.6 | 34.4 |
| Qwen3.5-27B | 42.2 | 39.8 | 20.9 | 34.3 |

## Examples and Tests

The [example files](examples/) illustrate the annotation format and dependency
scoring. They are synthetic examples, not benchmark samples.

```bash
pip install -e ".[dev]"
python -m videomembench.data examples/annotations.jsonl
python -m inference.metrics \
  --annotations examples/annotations.jsonl examples/results.jsonl
python -m pytest
```

The example scores are TurnAcc **75.00**, EpiDepAcc **100.00**, AnsDepAcc **0.00**,
and Overall **58.33**.

## Citation

```bibtex
@unpublished{videomembench,
  title  = {VideoMemBench: How Well Do MLLMs Remember in Video Conversations?},
  author = {Hu, Zhengdong and Wang, Chao and Feng, Kaituo and Yao, Huanjin
            and Lu, Mingfei and Fan, Hehe and Yang, Yi},
  note   = {Manuscript}
}
```

## License

VideoMemBench is available for **academic, non-commercial research**. Commercial
use and redistribution require prior written permission. Copyright in source videos
remains with their respective owners. See [LICENSE](LICENSE) for the full terms.
