import os
import sys
import tty
import termios
import threading
from speak import *
from listen import *
from llama_cpp import Llama
from ghost_client import *
import sys
sys.path.append("../PlanarAlly/ghost")
from commands import HELP_TEXT 
print(HELP_TEXT)
MAX_HISTORY = 20
FORMAT = '{"command": "", "source":""}'

llm = Llama(
    model_path="../../models/gemma-3-4b-it-q4_k_m.gguf",
    n_ctx= 2000
    
)

SYSTEM_PROMPT = f"""You are a command translator for a tabletop D&D game running on PlanarAlly.
A player will describe what they want to do, in their own words. Your only job
is to rewrite what they said into exactly one command line, using a shape from
the list below and the real names the player mentioned. Output nothing except
that one line: no explanation, no markdown, no bullet points, no quotation marks.

Valid command shapes:
{HELP_TEXT}

Rules:
- Use the exact character names the player said. Never invent, translate, or nickname them.
- The player must say which character is acting. If they don't name one, output: unclear
- A bare "attack" with no weapon, range, or spell named is not enough information.
  If melee, ranged, or cantrip isn't clear from what they said, output: unclear
- If the player is answering a yes/no question, output just "yes" or "no".
- If nothing above matches what they said, output exactly: unclear

Examples:
Player: "elf wants to hit the goblin with a sword"
You: elf melee attack on goblin

Player: "have the ranger shoot an arrow at the orc"
You: ranger ranged attack on orc

Player: "move gobbo closer to the dragon"
You: gobbo moves to dragon

Player: "how far away is the goblin from the elf"
You: measure from elf to goblin

Player: "yeah let's do it"
You: yes
"""


def llama_chat_commands(prompt, history):
    trimmed_history = history[-MAX_HISTORY:]
    response = llm.create_chat_completion(
        messages= [
            {f"role":"system", "content": SYSTEM_PROMPT},
            *trimmed_history
        ]
    )
    history.append({"role": "assistant", "content": response["choices"][0]["message"]["content"]})
    print(response["choices"][0]["message"]["content"])
    return(response["choices"][0]["message"]["content"])


def stop_program():
    print("'x' pressed, stopping.")
    os._exit(0)

def watch_for_stop_key(key='x'):
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        while True:
            ch = sys.stdin.read(1)
            if ch.lower() == key:
                stop_program()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def main():
    threading.Thread(target=watch_for_stop_key, daemon=True).start()
    #
    gameOn = True
    history = []
    while ( gameOn):
        #print("write message:")
        #user_input = input()
        user_input = listen_user()

        history.append({"role": "user", "content": user_input})
        print("history: ", history)
        output_text = llama_chat_commands(prompt=user_input, history=history)
        print("llama return: ", output_text)
        # speak(output_text)

if __name__=="__main__":
    main()