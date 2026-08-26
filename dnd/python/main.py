import os
import sys
from dotenv import load_dotenv

from speak import *
from listen import *
from llama_cpp import Llama
from ghost_client import *
from config import *
from pipeline import vet, narrate, lines_of

load_dotenv()
from config import *

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.join(SCRIPT_DIR, "..", "PlanarAlly", "ghost"))

from commands import HELP_TEXT, parse, ParseError
CURRENT_CHARACTERS = getReq()

MAX_HISTORY = 7
FORMAT = '{"command": "", "source":""}'

llm = Llama(
    model_path=os.path.normpath(os.path.join(SCRIPT_DIR, os.getenv('MODEL_PATH'))),
    n_ctx= 2000,
    n_gpu_layers=-1,  # offload all layers to Metal, at least works in mac
)

def llama_chat_commands(history):
    trimmed_history = history[-MAX_HISTORY:]
    print("thinking")
    response = llm.create_chat_completion(
        messages= [
            {f"role":"system", "content": build_system_prompt()},
            *trimmed_history
        ],
        max_tokens = 20,
    )
    history.append({"role": "assistant", "content": response["choices"][0]["message"]["content"]})
    print(response["choices"][0]["message"]["content"])
    return(response["choices"][0]["message"]["content"])

def llama_chat_narration(history):
    trimmed_history = history[-MAX_HISTORY:]
    print("thinking")
    response = llm.create_chat_completion(
        messages= [
            {f"role":"system", "content": SYSTEM_PROMPT_NARRATION},
            *trimmed_history
        ],
        max_tokens = 20,
    )
    history.append({"role": "assistant", "content": response["choices"][0]["message"]["content"]})
    print(response["choices"][0]["message"]["content"])
    return(response["choices"][0]["message"]["content"])

def cluster_chat(history):
    cluster_url = os.getenv('cluster_url')
    trimmed_history = history[-MAX_HISTORY:]
    message = {
        "model": "qwen3.6:latest",
        "stream": False,
        "think": False,
        "options": {"num_ctx": 32768, "temperature": 0.2},
        "messages": [
        {"role": "system", "content": build_system_prompt()},
        *trimmed_history,
        ]
    }

    try:
        res = post_to_cluster(cluster_url, message) # post to cluster, res in json
        content = res["message"]["content"]
        history.append({"role": "assistant", "content": content})
        return(content)
    except Exception as e:
        print("Error: ", e)

def main():
    #
    print("loading text to speech")
    warm_up()
    gameOn = True
    history = []

    while ( gameOn):
        # text input
        #print("write message:")
        #user_input = input()
        
        # audio input
        user_input = listen_user()

        history.append({"role": "user", "content": user_input})
        print("history: ", history)

        if CLUSTER_CHAT:
            output_llm = cluster_chat(history=history)
            print("cluster return: ", output_llm)
        else:
            output_llm = llama_chat_commands(history=history)
            print("llama return: ", output_llm)

        # Route on the tag the model answered with, not on whether the line
        # happens to parse. A question and a broken command both used to raise
        # ParseError, so a perfectly good question was discarded as noise.
        action, payload = vet(output_llm, user_input)

        if action == "say":      # a question back, or a refused command
            print("asking: ", payload)
            speak(payload)
            continue
        if action == "retry":
            print("rejected: ", payload)
            speak(payload)
            continue

        res = postReq({"command": payload, "source": "voice"})
        entry = res["entries"][0]
        res_move = lines_of(res)
        print(res_move)

        # The ghost is holding a question of its own -- a hazard to accept, or a
        # better place to stand that it has already drawn on the board. It reads
        # that question out itself, so nothing is spoken here; we only need to
        # stop and let the next utterance answer it, which vet() maps from
        # "yeah, go on" to a plain yes.
        if entry.get("awaiting"):
            continue

        # What actually happened. Without this the model only ever sees the
        # request and answers about that instead of about the result.
        history.append({"role": "user", "content": f"Result: {res_move}"})
        # Not spoken here. The ghost narrates every outcome it produces --
        # including the ones that arrive from this loop -- and it also covers the
        # in-game console and the action panel, which this loop never sees. Two
        # narrators meant every result read out twice, overlapping. Set
        # GHOST_MUTE=1 on the ghost to move the voice back to this side.

if __name__=="__main__":
    main()