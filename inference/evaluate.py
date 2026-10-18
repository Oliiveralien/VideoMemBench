"""Sequential self-rollout against OpenAI-compatible vision and grading endpoints."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from videomembench.data import load
from videomembench.dialogue import MCQ, TF, turn_type
from videomembench.llm import LLMConfig, chat, normalize_base_url
from videomembench.video import read_frames
from inference.prompts import EVAL_SYSTEM, choice_turn_text, open_turn_text
from inference.scoring import CHOICE_KEYS, gold_answers, judge_open, parse_choice, true_false_rule

PROTOCOL_VERSION = 'self-rollout-v1'

def evaluate_video(item: dict, args: argparse.Namespace) -> dict:
    model = LLMConfig(args.base_url, args.api_key, args.model, args.extra_body, args.timeout)
    judge = LLMConfig(args.judge_base_url, args.judge_api_key, args.judge_model, {}, args.timeout)
    rec = dict(video_id=item['video_id'], video_name=item['video_name'], model=args.model,
               judge_model=args.judge_model, protocol=PROTOCOL_VERSION, ok=False, per_turn=[])
    start = time.monotonic()
    try:
        frames, cache_hash = read_frames(args.frame_cache, item['video_name'], args.frames, args.resolution)
        rec.update(frame_cache_sha256=cache_hash, sampled_frames=len(frames)//2)
        messages = []
        for turn in item['dialogue']:
            typ, question = turn_type(turn), turn['question'].strip()
            is_choice = typ in (MCQ, TF) and bool(turn.get('options'))
            text = choice_turn_text(question, turn['options'], CHOICE_KEYS) if is_choice else open_turn_text(question)
            messages.append(dict(role='user', content=(frames if not messages else []) + [dict(type='text', text=text)]))
            # A failed model call aborts the dialogue: fabricated responses never enter history.
            pred = chat(model, messages, system=EVAL_SYSTEM, temperature=0.0, max_tokens=args.max_tokens)
            row = dict(turn_id=turn['turn_id'], type=typ, pred=pred)
            if is_choice:
                letter, method = parse_choice(pred)
                row.update(parsed=letter, parse_method=method, scorer='option_extraction',
                           correct=int(letter in turn['options'] and letter == turn['answer']))
            else:
                golds = gold_answers(turn)
                rule = true_false_rule(turn, golds, pred)
                if rule is not None:
                    row.update(correct=rule, scorer='tf_rule')
                else:
                    correct, error = judge_open(judge, question, golds, pred)
                    row.update(correct=correct, scorer='llm_judge')
                    if error:
                        # Keep output for debugging, but this record is never a completed result.
                        row['judge_error'] = 'grading failed; check endpoint and rerun'
                        rec['per_turn'].append(row)
                        raise RuntimeError('grading failed')
            rec['per_turn'].append(row)
            messages.append(dict(role='assistant', content=pred))
        rec['ok'] = True
    except Exception as e:
        # Do not persist endpoint exception bodies: they may echo authentication data.
        rec['error_type'] = type(e).__name__
    rec['elapsed_sec'] = round(time.monotonic()-start, 3)
    return rec

def parser(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config', help='TOML evaluation settings; CLI values override')
    ap.add_argument('--annotations')
    ap.add_argument('--frame-cache')
    ap.add_argument('--output', help='append-only JSONL result file')
    ap.add_argument('--model')
    ap.add_argument('--base-url', default=os.getenv('VMB_BASE_URL', ''))
    ap.add_argument('--judge-model', help='paper judge: GPT-5.4 mini; use your endpoint model ID')
    ap.add_argument('--judge-base-url', default=os.getenv('VMB_JUDGE_BASE_URL', ''))
    ap.add_argument('--api-key-env', default='VMB_API_KEY')
    ap.add_argument('--judge-api-key-env', default='VMB_JUDGE_API_KEY')
    ap.add_argument('--extra-body', default='{}', help='endpoint-specific request JSON')
    ap.add_argument('--frames', type=int, default=128, choices=[16,32,64,128])
    ap.add_argument('--resolution', type=int, default=512)
    ap.add_argument('--max-tokens', type=int, default=2048)
    ap.add_argument('--timeout', type=float, default=600.0)
    ap.add_argument('--workers', type=int, default=1, help='parallel videos; turns always sequential')
    pre, _ = ap.parse_known_args(argv)
    if pre.config:
        with open(pre.config, 'rb') as f:
            defaults = tomllib.load(f).get('evaluation', {})
        allowed = {a.dest for a in ap._actions} - {'help', 'config'}
        if set(defaults) - allowed:
            ap.error(f'unknown config keys: {sorted(set(defaults)-allowed)}')
        ap.set_defaults(**defaults)
    args = ap.parse_args(argv)
    for key in ('annotations','frame_cache','output','model','base_url','judge_model','judge_base_url'):
        if not getattr(args,key):
            ap.error(f'--{key.replace("_","-")} required (or supply in config)')
    if args.frames not in (16,32,64,128) or min(args.resolution,args.max_tokens,args.timeout,args.workers) <= 0:
        ap.error('invalid positive settings/frame budget')
    args.extra_body = json.loads(args.extra_body) if isinstance(args.extra_body,str) else args.extra_body
    if not isinstance(args.extra_body,dict):
        ap.error('extra-body must be a JSON object')
    if set(args.extra_body) & {'model','messages','temperature','max_tokens','stream'}:
        ap.error('extra-body must not override protocol request fields')
    args.base_url = normalize_base_url(args.base_url)
    args.judge_base_url = normalize_base_url(args.judge_base_url)
    args.api_key = os.getenv(args.api_key_env,'EMPTY')
    args.judge_api_key = os.getenv(args.judge_api_key_env,'EMPTY')
    return args

def run(args):
    items = load(args.annotations)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frames = {i['video_name']:read_frames(args.frame_cache,i['video_name'],args.frames,args.resolution)[1] for i in items}
    # Credentials and endpoint URLs are intentionally never serialized.
    settings = {k:getattr(args,k) for k in ('model','judge_model','frames','resolution','max_tokens','extra_body')}
    settings.update(protocol=PROTOCOL_VERSION, annotations_sha256=hashlib.sha256(Path(args.annotations).read_bytes()).hexdigest(),
                    frame_cache_sha256=frames)
    settings['run_id'] = hashlib.sha256(json.dumps(settings,sort_keys=True).encode()).hexdigest()
    manifest = output.with_suffix(output.suffix+'.manifest.json')
    if manifest.exists():
        if json.loads(manifest.read_text()) != settings:
            raise ValueError('run settings/data changed; choose a new output file')
    elif output.exists() and output.stat().st_size:
        raise ValueError('cannot resume results without their run manifest')
    else:
        manifest.write_text(json.dumps(settings,indent=2)+'\n')
    done = set()
    if output.exists():
        with output.open() as f:
            for line in f:
                if not line.strip(): continue
                record = json.loads(line)  # Refuse a damaged tail instead of hiding lost results.
                if record.get('run_id') != settings['run_id']:
                    raise ValueError('result run_id mismatch')
                if record.get('ok'):
                    done.add(record['video_name'])
    todo = [i for i in items if i['video_name'] not in done]
    print(f"Videos: {len(items)} / complete: {len(done)} / pending: {len(todo)}",flush=True)
    failures = 0
    with output.open('a') as f, ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(evaluate_video,i,args) for i in todo]
        for future in as_completed(futures):
            record = future.result()
            record['run_id'] = settings['run_id']
            f.write(json.dumps(record,ensure_ascii=False)+'\n'); f.flush()
            failures += int(not record['ok'])
            print(f"{record['video_name']}: {'complete' if record['ok'] else 'failed ('+record['error_type']+')'}",flush=True)
    if failures:
        raise SystemExit('Incomplete run: fix endpoint/video errors and repeat the same command to retry failed dialogues.')

def main():
    run(parser())

if __name__ == '__main__':
    main()
