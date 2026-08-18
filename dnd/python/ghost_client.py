import argparse
import requests

p = argparse.ArgumentParser(description="HTTP connection")
p.add_argument("--host", default="127.0.0.1", help="console bind address")
p.add_argument("--port", type=int, default=8770)
args = p.parse_args()

def postReq(message):
    res = requests.post(f"http://{args.host}:{args.port}/command", json=message)
    print("post response status: ", res.status_code)
    return res.json()

def getReq():
    res = requests.get(f"http://{args.host}:{args.port}/characters", )
    #print("get response: ", res.json()["characters"])
    # return list of characters
    return res.json()["characters"]

def post_to_cluster(url, payload):
    res = requests.post(url, json=payload)
    res.raise_for_status()
    return res.json()


#postReq({"command": "elf ranged attack on emo", "source":"voice "}