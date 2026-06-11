from __future__ import annotations

import argparse
import json
from urllib import request


def get(url):
    with request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    args = ap.parse_args()
    base = f"http://{args.host}:{args.port}"
    for path in ["/status", "/debug", "/channels", "/values"]:
        print("\n###", path)
        try:
            payload = get(base + path)
            print(json.dumps(payload, ensure_ascii=False, indent=2)[:6000])
        except Exception as exc:
            print("FAILED:", exc)


if __name__ == "__main__":
    main()
