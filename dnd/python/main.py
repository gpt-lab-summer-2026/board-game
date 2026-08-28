import os
import sys
import time
from dotenv import load_dotenv

from speak import *
from listen import *
from llama_cpp import Llama
from ghost_client import *
from config import *
from pipeline import vet, narrate, lines_of
from faults import Log, Flavour, report_outcome, wait_for_narration, lock_busy

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


# How long to let the ghost begin a monster's narration before deciding the
# monster run is over, and the ceiling on a single line. The ghost synthesises
# before it takes the speaker, and a cold Kokoro first line is slow, so the
# start wait is generous.
MONSTER_START_WAIT = float(os.getenv("MONSTER_START_WAIT", "12"))
MONSTER_LINE_MAX = float(os.getenv("MONSTER_LINE_MAX", "180"))
MONSTER_RUN_MAX = float(os.getenv("MONSTER_RUN_MAX", "300"))


def _await_one_narration():
    """Wait out a single spoken segment on the shared speaker.

    True if a line played; False if the ghost stayed silent long enough that the
    monster run looks finished. Unlike faults.wait_for_narration this never faults
    on silence -- silence is the signal the run is over, not a defect.
    """
    deadline = time.monotonic() + MONSTER_START_WAIT
    while time.monotonic() < deadline:
        if lock_busy():
            break
        time.sleep(0.1)
    else:
        return False  # nothing started -> the monster run is over
    end = time.monotonic() + MONSTER_LINE_MAX
    while time.monotonic() < end:
        if not lock_busy():
            time.sleep(0.4)  # let the sink drain before the next line
            return True
        time.sleep(0.1)
    return True


def wait_out_monster_turns(log):
    """Let the ghost play the monsters, one at a time, with the mic shut.

    Ported from autoplay.py. After a player's turn ends the initiative walks
    through the hostile creatures; the ghost runs each on its own (dm auto) and
    narrates it. Reopening the microphone in the middle of that is the bug the
    table sees twice over -- the narration goes straight back into the mic and
    can trip the wake word, and the turns pile up on top of each other. So we
    never open the mic during a monster run: we pace it from the shared speaker
    lock instead, waiting each monster's line out and re-checking whose turn it
    is, and only hand back to the listener once a party member is up again (or
    combat has ended).

    listen.py already ignores the wake word off-turn; this is the stronger
    guarantee that sits in front of it -- the mic stream is never even started
    while the monsters are acting.
    """
    if player_turn():
        return
    log.event("monster_turns_start")
    print("monsters are acting -- microphone held shut until it's a player's turn")
    began = time.monotonic()
    silent_runs = 0
    while not player_turn():
        if _await_one_narration():
            silent_runs = 0
            continue
        # The ghost has gone quiet but the tracker still shows a monster up.
        # One silent window is normal between turns; several in a row means the
        # run is either finished or wedged (dm auto off, a stuck turn), so hand
        # the mic back rather than trapping the human off-mic. The overall
        # ceiling is a second backstop.
        silent_runs += 1
        if silent_runs >= 2 or time.monotonic() - began > MONSTER_RUN_MAX:
            log.warn("MONSTER_TURNS_STALLED",
                     "ghost went quiet while a monster was still up; reopening the mic")
            break
        time.sleep(0.5)
    log.event("monster_turns_done")
    print("back to a player's turn")


def main():
    #
    print("loading text to speech")
    warm_up()
    gameOn = True
    history = []

    # Every fault this session gets a code, a line on the console and a row in
    # logs/voice-*.jsonl, so "it didn't work" can be looked up afterwards
    # instead of remembered.
    log = Log()
    flavour = Flavour(log)
    log.event("session_start", cluster_chat=bool(CLUSTER_CHAT),
              flavour=flavour.enabled, flavour_model=flavour.model)

    try:
        while gameOn:
            # Before opening the mic, let the ghost play out any monster turns
            # one at a time, off-mic. This is the autoplay pacing: the human has
            # nothing to do on a goblin's turn, so we do not listen then -- no
            # wake word over the enemy turns, and no burst of turns talking over
            # each other.
            wait_out_monster_turns(log)

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

            # Name the failure. A wall in the way and a spent action are the rules
            # working; a traceback out of the ghost is not, and reporting them the
            # same way trains you to ignore both. Codes go to logs/voice-*.jsonl.
            report_outcome(log, payload, entry)

            # Start the flavour sentence now, on a worker thread, so the cluster
            # round trip happens *while* the ghost reads the numbers out and costs
            # no wall-clock. Bookkeeping ("next turn") is skipped -- asked to narrate
            # one, the model invents a spell nobody cast.
            pending_flavour = flavour.start(payload, entry.get("lines") or [])

            # The ghost is holding a question of its own -- a hazard to accept, or a
            # better place to stand that it has already drawn on the board. It reads
            # that question out itself, so nothing is spoken here; we only need to
            # stop and let the next utterance answer it, which vet() maps from
            # "yeah, go on" to a plain yes. Wait for it to finish asking first, or
            # the microphone opens while the question is still being read out.
            if entry.get("awaiting"):
                wait_for_narration(log, expected=True)
                flavour.finish(pending_flavour, timeout=1)
                continue

            # Do not go back to listening while the ghost is still talking. The
            # speaker and the microphone are in the same room: its narration goes
            # straight back into the mic, and on a bad day trips the wake word.
            wait_for_narration(log, expected=bool(entry.get("lines")))

            # The story, on top of the mechanics the ghost just read out. "freak
            # takes 11, down to 2" is the result; this is what it looked like.
            told = flavour.finish(pending_flavour)
            if told:
                print("narration: ", told)
                log.event("flavour", command=payload, text=told)
                speak(told)

            # What actually happened. Without this the model only ever sees the
            # request and answers about that instead of about the result.
            history.append({"role": "user", "content": f"Result: {res_move}"})
            # The mechanics are not spoken here. The ghost narrates every outcome it
            # produces -- including the ones that arrive from this loop -- and it
            # also covers the in-game console and the action panel, which this loop
            # never sees. Two narrators meant every result read out twice,
            # overlapping. Set GHOST_MUTE=1 on the ghost to move the voice back to
            # this side.

    except KeyboardInterrupt:
        log.warn("INTERRUPTED", "stopped by hand")
    finally:
        log.summary()


if __name__=="__main__":
    main()