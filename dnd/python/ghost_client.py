import argparse
import requests

def send(message, args):
    res = requests.post(f"http://{args.host}:{args.port}/command", json=message)
    print(res.status_code)
    return res


def main():
    p = argparse.ArgumentParser(description="HTTP connection")
    p.add_argument("--host", default="127.0.0.1", help="console bind address")
    p.add_argument("--port", type=int, default=8770)
    args = p.parse_args()

    
    send({"command":"meele","source":"text"}, args)

if __name__ == "__main__":
    main()