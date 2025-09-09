import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
import wave

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def now_iso() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def load_model(name: str, device: str, compute_type: str):
    try:
        from faster_whisper import WhisperModel
    except Exception:
        sys.path.insert(0, os.path.join(ROOT_DIR, 'faster-whisper'))
        from faster_whisper import WhisperModel  # type: ignore
    # Try desired compute_type, then fallbacks commonly available on CPU/GPU
    candidates = [compute_type, 'int8', 'float16', 'float32']
    tried = []
    for ct in candidates:
        if ct in tried:
            continue
        tried.append(ct)
        try:
            print(f"[asr] loading model={name} device={device} compute={ct}", file=sys.stderr)
            return WhisperModel(name, device=device, compute_type=ct)
        except Exception as e:
            print(f"[asr] load failed for compute={ct}: {e}", file=sys.stderr)
            last_err = e
            continue
    raise RuntimeError(f"failed to load faster-whisper with compute in {candidates}: {last_err}")

def transcribe_file(model, path: str, language: str = 'zh', beam_size: int = 1):
    try:
        segments, info = model.transcribe(path, language=language, beam_size=beam_size)
        text = ''.join(seg.text for seg in segments)
        return {
            'text': text.strip(),
            'duration': getattr(info, 'duration', None),
            'language': getattr(info, 'language', language),
        }
    except Exception as e:
        return {'error': str(e)}

def watch_and_transcribe(args):
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    model = load_model(args.model, args.device, args.compute)
    seen = set()
    try:
        while True:
            now = time.time()
            names = sorted([n for n in os.listdir(args.watch) if n.lower().endswith('.wav')])
            # Avoid reading the newest file (likely still being written)
            newest = names[-1] if names else None
            for name in names:
                if name == newest:
                    continue
                if not name.lower().endswith('.wav'):
                    continue
                p = os.path.join(args.watch, name)
                if p in seen:
                    continue
                # Skip files still being written: require age > 2.5s and stable size
                try:
                    age = now - os.path.getmtime(p)
                    if age < 2.5:
                        continue
                    s1 = os.path.getsize(p)
                    time.sleep(0.1)
                    s2 = os.path.getsize(p)
                    if s1 != s2:
                        continue
                except FileNotFoundError:
                    continue
                # Validate WAV header before sending to ASR (skip if invalid)
                try:
                    with wave.open(p, 'rb') as wf:
                        _ = wf.getnframes()
                except Exception:
                    # Not a valid/complete WAV yet; try later
                    continue
                seen.add(p)
                res = transcribe_file(model, p, language=args.lang)
                rec = {
                    'ts': now_iso(),
                    'file': p,
                    'result': res,
                }
                with open(args.out, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(rec, ensure_ascii=False) + '\n')
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--watch', required=True, help='Directory of wav segments to watch')
    ap.add_argument('--out', required=True, help='Output JSONL path')
    ap.add_argument('--model', default=os.environ.get('FWHISPER_MODEL', 'small'))
    ap.add_argument('--device', default=os.environ.get('FWHISPER_DEVICE', 'auto'))
    ap.add_argument('--compute', default=os.environ.get('FWHISPER_COMPUTE', 'int8'))
    ap.add_argument('--lang', default=os.environ.get('FWHISPER_LANG', 'zh'))
    args = ap.parse_args()
    watch_and_transcribe(args)

if __name__ == '__main__':
    main()
