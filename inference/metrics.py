from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from videomembench.dialogue import answer_ancestors, answer_parents, episodic_parents, parents


def load_annotations(path: str) -> dict[str, list[dict]]:
    from videomembench.data import load
    return {item["video_name"]: item["dialogue"] for item in load(path)}


def load_results(path: str) -> tuple[dict[tuple[str, str], int], dict]:
    latest = {}
    audit = {"judge_errors": 0, "call_errors": 0, "failed_videos": 0, "bad_lines": 0}
    run_ids = set()
    with open(path, encoding="utf8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                audit["bad_lines"] += 1
                continue
            if not rec.get("video_name"):
                raise ValueError("result record missing video_name")
            if rec.get("oracle_history"):
                raise ValueError("oracle histories cannot be scored as self-rollout")
            if rec.get("run_id"):
                run_ids.add(rec['run_id'])
            if len(run_ids) > 1:
                raise ValueError("mixed run IDs in result file")
            latest[rec['video_name']] = rec
    correct = {}
    for video, rec in latest.items():
        if not rec.get('ok'):
            audit['failed_videos'] += 1
            continue
        seen = set()
        for t in rec.get('per_turn', []):
            tid = str(t.get('turn_id'))
            if tid in seen:
                raise ValueError('duplicate turn result')
            seen.add(tid)
            v = t.get('correct')
            if type(v) not in (int, bool) or v not in (0,1):
                raise ValueError('correctness must be binary')
            correct[(video,tid)] = int(v)
            audit['judge_errors'] += int('judge_error' in t)
            audit['call_errors'] += int('call_error' in t)
    return correct, audit


def compute(dialogues: dict[str, list[dict]], correct: dict[tuple[str, str], int]) -> dict:
    expected = {(v, str(t["turn_id"])) for v, ts in dialogues.items() for t in ts}
    if set(correct) - expected:
        raise ValueError("results contain unknown video/turn IDs")
    turn = [0, 0]; epi = [0, 0]; ans = [0, 0]; ind = [0, 0]
    missing = 0
    for video, dialogue in dialogues.items():
        for t in dialogue:
            tid = str(t.get("turn_id"))
            key = (video, tid)
            if key not in correct:
                missing += 1
            ok = correct.get(key, 0)
            turn[0] += ok; turn[1] += 1
            if not parents(t):
                ind[0] += ok; ind[1] += 1
            if episodic_parents(t):
                epi[0] += ok; epi[1] += 1
            if answer_parents(t):
                chain_ok = ok and all(correct.get((video, a), 0) for a in answer_ancestors(dialogue, tid))
                ans[0] += int(bool(chain_ok)); ans[1] += 1

    def pct(x):
        return 100.0 * x[0] / x[1] if x[1] else None

    m = {"TurnAcc": pct(turn), "EpiDepAcc": pct(epi), "AnsDepAcc": pct(ans), "IndepAcc": pct(ind)}
    m["Overall"] = sum(m[c] for c in ("TurnAcc", "EpiDepAcc", "AnsDepAcc")) / 3 if all(m[c] is not None for c in ("TurnAcc", "EpiDepAcc", "AnsDepAcc")) else None
    m["Dep"] = (m["EpiDepAcc"] + m["AnsDepAcc"]) / 2 if m["EpiDepAcc"] is not None and m["AnsDepAcc"] is not None else None
    m["n"] = {"turns": turn[1], "episodic": epi[1], "answer": ans[1], "independent": ind[1], "missing": missing}
    return m


COLS = ['TurnAcc', 'EpiDepAcc', 'AnsDepAcc', 'Overall']

def main():
    import csv
    ap = argparse.ArgumentParser(description='Paper metrics (percent), pooled across turns')
    ap.add_argument('--annotations', required=True)
    ap.add_argument('--format', choices=['markdown','json','csv'], default='markdown')
    ap.add_argument('--allow-incomplete', action='store_true', help='diagnostics only: missing/failed turns count as wrong')
    ap.add_argument('evals', nargs='+')
    args = ap.parse_args()
    dialogues = load_annotations(args.annotations)
    rows = []
    for path in args.evals:
        from pathlib import Path
        import hashlib
        manifest = Path(path + '.manifest.json')
        if manifest.exists():
            recorded = json.loads(manifest.read_text())
            digest = hashlib.sha256(Path(args.annotations).read_bytes()).hexdigest()
            if recorded.get('annotations_sha256') != digest:
                raise SystemExit('scoring annotations do not match the run manifest')
        correct, audit = load_results(path)
        metrics = compute(dialogues, correct)
        incomplete = bool(metrics['n']['missing'] or any(audit.values()))
        if incomplete and not args.allow_incomplete:
            raise SystemExit(f'{path}: incomplete or errored results; rerun evaluation or use --allow-incomplete for diagnostics')
        if incomplete:
            print(f'WARNING {path}: incomplete diagnostic score; {audit}',file=sys.stderr)
        rows.append(dict(model=os.path.basename(os.path.dirname(os.path.abspath(path))),
                         **metrics, audit=audit, complete=not incomplete))
    rows.sort(key=lambda r: -(r['Overall'] if r['Overall'] is not None else -1))
    if args.format == 'json':
        print(json.dumps(rows,indent=2,allow_nan=False))
    elif args.format == 'csv':
        w = csv.writer(sys.stdout)
        w.writerow(['model',*COLS,'complete'])
        for r in rows:
            w.writerow([r['model'],*[r[c] for c in COLS],r['complete']])
    else:
        print('| Model | '+' | '.join(COLS)+' | Complete |')
        print('|---|'+'---:|'*len(COLS)+'---|')
        for r in rows:
            values = ['N/A' if r[c] is None else f'{r[c]:.2f}' for c in COLS]
            print('| '+r['model']+' | '+' | '.join(values)+' | '+str(r['complete'])+' |')

if __name__ == '__main__':
    main()
