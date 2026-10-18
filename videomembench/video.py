"""Freeze full-video timestamped frames once, then share the cache across models."""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import json
import math
import os
import tempfile
from pathlib import Path

ALGORITHM = 'uniform-round-endpoints-v1'

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def sample_indices(total_frames: int, count: int = 128) -> list[int]:
    if total_frames <= 0 or count < 2:
        raise ValueError('positive video length and at least two samples required')
    # Exact budget for short clips as well: repeated indices are intentional.
    return [round(i * (total_frames - 1) / (count - 1)) for i in range(count)]

def resolve_video(root: str, name: str) -> Path:
    base = Path(root).resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError(f'video must exist inside --video-root: {name}')
    return path

def cache_path(cache_root: str, name: str) -> Path:
    return Path(cache_root) / hashlib.sha256(name.encode()).hexdigest()[:24] / 'frames.json'

def freeze(root: str, cache_root: str, name: str, count: int = 128, resolution: int = 512) -> dict:
    import cv2
    from PIL import Image
    path = resolve_video(root, name)
    dest = cache_path(cache_root, name)
    source_hash = sha256(path)
    if dest.exists():
        rec = json.loads(dest.read_text())
        if (rec.get('video_sha256'), rec.get('count'), rec.get('resolution'), rec.get('algorithm')) != (
                source_hash, count, resolution, ALGORITHM):
            raise ValueError('cache settings/video changed; use a different cache directory')
        read_frames(cache_root, name, count, resolution)
        return rec
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise ValueError(f'cannot decode {name}')
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        if not math.isfinite(fps) or fps <= 0:
            raise ValueError('video has invalid FPS; normalize the video before evaluation')
        indices = sample_indices(n, count)
        dest.parent.mkdir(parents=True, exist_ok=True)
        frames = []
        for i, idx in enumerate(indices):
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, frame = cap.read()
            if not ok or frame is None:
                raise ValueError(f'frame {idx} did not decode; no partial cache accepted')
            image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            image.thumbnail((resolution, resolution), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            image.save(buf, format='JPEG', quality=75, optimize=True)
            blob = buf.getvalue()
            file = f'{i:03d}.jpg'
            (dest.parent/file).write_bytes(blob)
            frames.append(dict(file=file, index=idx, timestamp_sec=idx/fps,
                               sha256=hashlib.sha256(blob).hexdigest()))
        rec = dict(video_name=name, video_sha256=source_hash, count=count, resolution=resolution,
                   algorithm=ALGORITHM, fps=fps, total_frames=n, frames=frames)
        with tempfile.NamedTemporaryFile('w', dir=dest.parent, delete=False) as f:
            json.dump(rec, f, indent=2)
            temp = f.name
        os.replace(temp, dest)
        return rec
    finally:
        cap.release()

def read_frames(cache_root: str, name: str, count: int, resolution: int) -> tuple[list[dict], str]:
    path = cache_path(cache_root, name)
    raw = path.read_bytes()
    rec = json.loads(raw)
    if rec.get('algorithm') != ALGORITHM or rec.get('count') != count or rec.get('resolution') != resolution or len(rec['frames']) != count:
        raise ValueError('frame cache does not match requested protocol')
    content = []
    for frame in rec['frames']:
        file = (path.parent/frame['file']).resolve()
        if not file.is_relative_to(path.parent.resolve()):
            raise ValueError('invalid frame file')
        blob = file.read_bytes()
        if hashlib.sha256(blob).hexdigest() != frame['sha256']:
            raise ValueError('frame checksum mismatch')
        seconds = int(frame['timestamp_sec'])
        mm, ss = divmod(seconds, 60)
        hh, mm2 = divmod(mm, 60)
        stamp = f'{hh:02d}:{mm2:02d}:{ss:02d}' if hh else f'{mm:02d}:{ss:02d}'
        content += [dict(type='text', text=f'<{stamp}>'),
                    dict(type='image_url', image_url=dict(url='data:image/jpeg;base64,'+base64.b64encode(blob).decode()))]
    return content, hashlib.sha256(raw).hexdigest()

def main():
    from .data import load
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--annotations', required=True)
    ap.add_argument('--video-root', required=True)
    ap.add_argument('--frame-cache', required=True)
    ap.add_argument('--frames', type=int, default=128, choices=[16,32,64,128])
    ap.add_argument('--resolution', type=int, default=512)
    args = ap.parse_args()
    if args.resolution < 1:
        ap.error('resolution must be positive')
    for item in load(args.annotations):
        rec = freeze(args.video_root, args.frame_cache, item['video_name'], args.frames, args.resolution)
        print(f"Frozen {rec['video_name']}: {rec['count']} frames")

if __name__ == '__main__':
    main()
