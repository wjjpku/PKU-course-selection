"""Offline benchmark of the shipped model; never contacts the elective website."""
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from autoelective.captcha import CaptchaRecognizer
from autoelective.const import CNN_MODEL_FILE


def main():
    start = time.perf_counter()
    recognizer = CaptchaRecognizer()
    load_ms = (time.perf_counter() - start) * 1000
    rows = []
    for path in sorted((ROOT / 'test' / 'data').glob('*.jpg')):
        data = path.read_bytes()
        expected = path.stem.split('_')[0]
        start = time.perf_counter()
        actual = recognizer.recognize(data).code
        rows.append(dict(file=path.name, expected=expected, actual=actual,
                         correct=actual == expected,
                         latency_ms=round((time.perf_counter() - start) * 1000, 2)))
    result = dict(model_sha256=hashlib.sha256(Path(CNN_MODEL_FILE).read_bytes()).hexdigest(),
                  model_load_ms=round(load_ms, 2), total=len(rows),
                  correct=sum(row['correct'] for row in rows),
                  median_ms=statistics.median(row['latency_ms'] for row in rows),
                  samples=rows)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not rows or not all(row['correct'] for row in rows):
        sys.exit(1)


if __name__ == '__main__':
    main()
