import argparse
import requests

def postReq(message):
    p = argparse.ArgumentParser(description="HTTP connection")
    p.add_argument("--host", default="127.0.0.1", help="console bind address")
    p.add_argument("--port", type=int, default=8770)
    args = p.parse_args()

    res = requests.post(f"http://{args.host}:{args.port}/command", json=message)
    print(res.status_code)
    return res

