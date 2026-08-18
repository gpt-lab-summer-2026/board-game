import os
import sys
from dotenv import load_dotenv

from speak import *
from listen import *
from llama_cpp import Llama
from ghost_client import *
from config import *

load_dotenv()
from config import *

load_dotenv()

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

        # check output kind
        try:
            parse(output_llm)
            res = postReq({"command": output_llm, "source":"voice"}) #post command and response in json
            res_move = ' '.join(res["entries"][0]["lines"])
            print(res_move)

            if CLUSTER_CHAT:
                narration = cluster_chat(history=history)
            else:
                narration = llama_chat_commands(history=history)

            print(narration)
            speak(narration)
        except ParseError:
            speak("Unclear, try again!")

if __name__=="__main__":
    main()