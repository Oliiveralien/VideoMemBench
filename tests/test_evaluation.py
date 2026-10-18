"""Regression tests for protocol semantics, not model quality."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from inference.metrics import compute, load_results
from videomembench.data import load, validate
from videomembench.dialogue import answer_ancestors
from videomembench.video import sample_indices

ROOT = Path(__file__).resolve().parents[1]

def dataset():
    return load(str(ROOT/'examples/annotations.jsonl'))

def test_paper_fixture():
    dialogues = {i['video_name']:i['dialogue'] for i in dataset()}
    correct, audit = load_results(str(ROOT/'examples/results.jsonl'))
    m = compute(dialogues, correct)
    assert m['TurnAcc'] == 75
    assert m['EpiDepAcc'] == 100
    assert m['AnsDepAcc'] == 0
    assert m['Overall'] == pytest.approx(175/3)
    assert m['n'] == dict(turns=4, episodic=2, answer=2, independent=1, missing=0)
    assert not any(audit.values())

def node(tid, **parents):
    return dict(turn_id=tid, dependency=dict(depends_on=list(parents),dep_type=parents))

def test_answer_traversal_excludes_episodic_at_every_depth():
    turns = [node('T1'),node('T2',T1='episodic'),node('T3',T2='answer'),
             node('T4',T1='answer'),node('T5',T3='answer',T4='episodic')]
    assert answer_ancestors(turns,'T3') == {'T2'}
    assert answer_ancestors(turns,'T5') == {'T3','T2'}
    # T1 and T4 being wrong must not remove T3 or T5 chain credit.
    m = compute({'v':turns},{('v',f'T{i}'):int(i in (2,3,5)) for i in range(1,6)})
    assert m['AnsDepAcc'] == pytest.approx(200/3)
    assert m['EpiDepAcc'] == 100

def test_multiple_answer_parents_and_transitive_failure():
    turns=[node('T1'),node('T2'),node('T3',T1='answer',T2='answer'),node('T4',T3='answer')]
    assert answer_ancestors(turns,'T4') == {'T1','T2','T3'}
    m=compute({'v':turns},{('v',f'T{i}'):int(i!=2) for i in range(1,5)})
    assert m['AnsDepAcc']==0
    assert m['EpiDepAcc'] is None and m['Overall'] is None

def test_pool_turns_not_video_means_and_missing_denominator():
    ds={'short':[node('T1')],'long':[node(f'T{i}') for i in range(1,4)]}
    m=compute(ds,{('short','T1'):1})
    assert m['TurnAcc']==25 and m['n']['missing']==3
    with pytest.raises(ValueError): compute(ds,{('unknown','T1'):1})

@pytest.mark.parametrize('count',[16,32,64,128])
def test_uniform_budget_and_endpoints(count):
    for n in (1,4,128,10000):
        xs=sample_indices(n,count)
        assert len(xs)==count and xs[0]==0 and xs[-1]==n-1
        assert xs==sorted(xs) and xs==sample_indices(n,count)

@pytest.mark.parametrize('mutator',[
    lambda i:i['dialogue'][1]['dependency']['dep_type'].update(T1='unknown'),
    lambda i:i['dialogue'][1]['dependency']['depends_on'].append('T4'),
    lambda i:i['dialogue'][0].update(question=''),
    lambda i:i['dialogue'][0].update(answer='Z'),
    lambda i:i['dialogue'][0].update(turn_id='T2'),
    lambda i:i.update(private_metadata='should not be exported'),
])
def test_invalid_annotations_rejected(mutator):
    item=dataset()[0]
    mutator(item)
    with pytest.raises(ValueError): validate([item])

def test_latest_attempt_used_without_stale_turns(tmp_path):
    p=tmp_path/'r.jsonl'
    records=[dict(video_name='v',ok=True,per_turn=[dict(turn_id='T1',correct=1)]),
             dict(video_name='v',ok=False,error_type='RuntimeError'),
             dict(video_name='other',ok=False)]
    p.write_text('\n'.join(json.dumps(r) for r in records))
    correct,audit=load_results(str(p))
    assert correct=={} and audit['failed_videos']==2
    records.append(dict(video_name='v',ok=True,per_turn=[dict(turn_id='T1',correct=0)]))
    p.write_text('\n'.join(json.dumps(r) for r in records))
    correct,audit=load_results(str(p))
    assert correct=={('v','T1'):0} and audit['failed_videos']==1

@pytest.mark.parametrize('records',[
    [dict(video_name='v',ok=True,oracle_history=True)],
    [dict(video_name='v',ok=True,run_id='a'),dict(video_name='w',ok=True,run_id='b')],
    [dict(video_name='v',ok=True,per_turn=[dict(turn_id='T1',correct=2)])],
    [dict(video_name='v',ok=True,per_turn=[dict(turn_id='T1',correct=1)]*2)],
])
def test_invalid_results_rejected(tmp_path,records):
    p=tmp_path/'r.jsonl';p.write_text('\n'.join(json.dumps(r) for r in records))
    with pytest.raises(ValueError):load_results(str(p))

def args(tmp_path):
    return SimpleNamespace(base_url='http://localhost:8000/v1',api_key='PRIVATE',model='test',
        extra_body={},timeout=5,judge_base_url='http://localhost:8001/v1',judge_api_key='JUDGE_PRIVATE',
        judge_model='test-judge',frames=128,resolution=512,max_tokens=2048,workers=1,
        frame_cache=str(tmp_path/'cache'),annotations=str(ROOT/'examples/annotations.jsonl'),
        output=str(tmp_path/'run/eval.jsonl'))

def test_own_responses_and_visual_context_never_gold(tmp_path):
    import inference.evaluate as ev
    item=dataset()[0];a=args(tmp_path);requests=[]
    replies=['\\boxed{B}','\\boxed{a guessed location}','\\boxed{B}','\\boxed{unknown}']
    def model(cfg,messages,**kw):
        requests.append(copy.deepcopy(messages))
        assert kw['temperature']==0 and kw['max_tokens']==2048
        return replies[len(requests)-1]
    frame=[dict(type='image_url',image_url={'url':'data:image/jpeg;base64,SYNTHETIC'})]*128
    with patch.object(ev,'read_frames',return_value=(frame,'hash')),patch.object(ev,'chat',side_effect=model),patch.object(ev,'judge_open',return_value=(0,None)):
        record=ev.evaluate_video(item,a)
    assert record['ok'] and len(requests)==4
    for t,messages in enumerate(requests):
        assert len(messages)==2*t+1
        assert sum(p['type']=='image_url' for m in messages if isinstance(m['content'],list) for p in m['content'])==128
        assert [m['content'] for m in messages if m['role']=='assistant']==replies[:t]
        all_content=json.dumps(messages)
        assert 'To the left of the box.' not in all_content and 'A small plate.' not in all_content
        assert 'dep_type' not in all_content

@pytest.mark.parametrize('failure',['model','judge'])
def test_failure_aborts_dialogue_and_never_finishes(tmp_path,failure):
    import inference.evaluate as ev
    item=dataset()[0];a=args(tmp_path)
    with patch.object(ev,'read_frames',return_value=([], 'hash')),patch.object(ev,'chat',side_effect=RuntimeError('secret') if failure=='model' else None,return_value='A') as model,patch.object(ev,'judge_open',return_value=(0,'private failure')):
        rec=ev.evaluate_video(item,a)
    assert not rec['ok'] and model.call_count==(1 if failure=='model' else 2)
    assert 'secret' not in json.dumps(rec) and 'private failure' not in json.dumps(rec)

def test_resume_does_not_recall_and_rejects_drift(tmp_path):
    import inference.evaluate as ev
    a=args(tmp_path)
    good=dict(video_name='synthetic-demo.mp4',ok=True,per_turn=[])
    with patch.object(ev,'read_frames',return_value=([],'hash')),patch.object(ev,'evaluate_video',return_value=good) as run:
        ev.run(a);ev.run(a)
        assert run.call_count==1
        a.model='different'
        with pytest.raises(ValueError,match='changed'): ev.run(a)
    assert 'PRIVATE' not in Path(a.output+'.manifest.json').read_text()
    assert 'http' not in Path(a.output+'.manifest.json').read_text()

def test_config_override_and_key_not_serialized(tmp_path,monkeypatch):
    from inference.evaluate import parser
    cfg=tmp_path/'config.toml'
    cfg.write_text('[evaluation]\nmodel="config-model"\nannotations="a"\nframe_cache="c"\noutput="o"\nbase_url="http://localhost/v1"\njudge_model="j"\njudge_base_url="http://localhost/judge/v1"\nframes=128\n')
    monkeypatch.setenv('VMB_API_KEY','SECRET')
    a=parser(['--config',str(cfg),'--model','cli-model'])
    assert a.model=='cli-model' and a.api_key=='SECRET'
    with pytest.raises(SystemExit):parser(['--config',str(cfg),'--extra-body','{"messages":[]}'])

@pytest.mark.parametrize('raw,expected,method',[
    ('\\boxed{C}','C','boxed'),('{"answer":"B"}','B','json'),
    ('"a"','A','json'),('D','D','bare_letter'),
    ('Final answer: B','B','regex_letter'),('No option selected',None,'unparsed')])
def test_choice_parser(raw,expected,method):
    from inference.scoring import parse_choice
    assert parse_choice(raw)==(expected,method)

def test_open_grading_strict_json_and_retry():
    import inference.scoring as scoring
    with patch.object(scoring,'chat',side_effect=['{"correct":1,"score":0}','{"correct":1,"score":1,"reason":"match"}']):
        assert scoring.judge_open(None,'Question',['Reference'],'Prediction')==(1,None)
    with patch.object(scoring,'chat',return_value='{"correct":true,"score":0.5}'):
        correct,error=scoring.judge_open(None,'Q',['R'],'P',attempts=1)
        assert correct==0 and error

def test_boolean_legacy_rule():
    from inference.scoring import true_false_rule
    turn=dict(type='true_or_false_question')
    assert true_false_rule(turn,['true'],'No, wait: \\boxed{yes}')==1
    assert true_false_rule(turn,['false'],'\\boxed{yes}')==0

def test_real_video_cache_and_tamper_detection(tmp_path):
    import cv2
    import numpy as np
    from videomembench.video import freeze,read_frames,cache_path
    video=tmp_path/'tiny.avi'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),4,(32,24))
    assert writer.isOpened()
    for value in (0,80,160,240):writer.write(np.full((24,32,3),value,dtype=np.uint8))
    writer.release()
    cache=str(tmp_path/'cache')
    rec=freeze(str(tmp_path),cache,'tiny.avi')
    assert rec['count']==128 and len(rec['frames'])==128
    content,digest=read_frames(cache,'tiny.avi',128,512)
    assert len(content)==256 and len(digest)==64
    assert freeze(str(tmp_path),cache,'tiny.avi')==rec
    with pytest.raises(ValueError):freeze(str(tmp_path),cache,'tiny.avi',32)
    first=cache_path(cache,'tiny.avi').parent/'000.jpg'
    first.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='checksum'):read_frames(cache,'tiny.avi',128,512)

def test_sdk_end_to_end_with_frozen_video_and_fake_transport(tmp_path):
    """Real video decode + SDK wire format + grading + resume + metric report, no network."""
    import cv2
    import numpy as np
    import httpx
    from openai import OpenAI
    import inference.evaluate as ev
    import videomembench.llm as llm
    from videomembench.video import freeze
    a=args(tmp_path)
    item=dataset()[0];item['video_name']='demo.avi'
    annotations=tmp_path/'annotations.jsonl'
    annotations.write_text(json.dumps(item)+'\n');a.annotations=str(annotations)
    video=tmp_path/'demo.avi'
    writer=cv2.VideoWriter(str(video),cv2.VideoWriter_fourcc(*'MJPG'),4,(32,24))
    assert writer.isOpened()
    for value in (20,80,160,240):writer.write(np.full((24,32,3),value,dtype=np.uint8))
    writer.release()
    freeze(str(tmp_path),a.frame_cache,item['video_name'])
    responses=['\\boxed{B}','\\boxed{To the left of the box.}','\\boxed{A}','\\boxed{A small plate.}']
    model_calls=[];judge_calls=[]
    def respond(request):
        body=json.loads(request.content)
        if body['model']==a.model:
            idx=len(model_calls);model_calls.append(body)
            assert len(body['messages'])==2*idx+2  # system + full history
            assert sum(p['type']=='image_url' for m in body['messages'] if isinstance(m['content'],list) for p in m['content'])==128
            assert [m['content'] for m in body['messages'] if m['role']=='assistant']==responses[:idx]
            text=responses[idx]
        else:
            judge_calls.append(body)
            assert body['response_format']=={'type':'json_object'}
            text='{"correct":1,"score":1,"reason":"equivalent"}'
        return httpx.Response(200,json={'id':'test','object':'chat.completion','created':0,'model':body['model'],
            'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':text}}]})
    transport=httpx.MockTransport(respond)
    clients={}
    for url,key in ((a.base_url,a.api_key),(a.judge_base_url,a.judge_api_key)):
        clients[(url,key,a.timeout)]=OpenAI(base_url=url,api_key=key,http_client=httpx.Client(transport=transport))
    try:
        with patch.dict(llm._CLIENTS,clients,clear=True):
            ev.run(a);ev.run(a)
        assert len(model_calls)==4 and len(judge_calls)==2
        correct,audit=load_results(a.output)
        m=compute({item['video_name']:item['dialogue']},correct)
        assert m['Overall']==pytest.approx(175/3)
        assert not any(audit.values())
        manifest=json.loads(Path(a.output+'.manifest.json').read_text())
        assert manifest['frames']==128 and manifest['protocol']=='self-rollout-v1'
        assert len(manifest['frame_cache_sha256'])==1
    finally:
        for client in clients.values(): client.close()
