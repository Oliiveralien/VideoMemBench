# Examples

`annotations.jsonl` illustrates the evaluation schema with a four-turn dialogue.
`results.jsonl` provides corresponding scoring inputs. These are synthetic examples;
a matching video is not included.

```bash
python -m videomembench.data examples/annotations.jsonl
python -m inference.metrics --annotations examples/annotations.jsonl examples/results.jsonl
```

Expected scores: TurnAcc **75.00**, EpiDepAcc **100.00**, AnsDepAcc **0.00**,
and Overall **58.33**.

T3 is individually correct but receives no Answer-chain credit because T1 is wrong.
T4 also loses chain credit through T3 → T1. Its Episodic edge to T2 is excluded
from Answer-ancestor traversal. T4 contributes to both dependency subsets.
