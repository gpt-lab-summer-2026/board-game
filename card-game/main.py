import cv2
import json
import rapidfuzz as fuzz
import random
import threading

from llama_cpp import Llama

from text_detection import *
from speak import *
from camera import *
from config import *

llm = Llama(
    model_path="../models/gemma-3-4b-it-q4_k_m.gguf",
    n_ctx= 2000,
    n_gpu_layers=-1,  # offload all layers to Metal, at least works in mac
)

def llama_chat(black_card, pick_number, player_cards):
    print("thinking")
    response = llm.create_chat_completion(
        messages= [
            {"role": "system", "content": (
                "You are the dealer in a game of Cards Against Humanity. "
                "The black card has one or more blanks, shown as underscores ('_'). "
                "Each player has submitted white card(s) to fill those blanks. "
                "Pick the funniest submission, then talk about it casually and naturally, "
                "like you're chatting with friends after a round, not writing a formal review."
            )},
            {"role": "user", "content": (
                f"Black card: {black_card}\n"
                f"Number of blanks to fill: {pick_number}\n"
                f"Player submissions (each item is one player's card, or cards if more than one blank): {player_cards}\n\n"
                "Reply with exactly two short parts:\n"
                "1. The black card text with the blank(s) filled in using the winning player's card(s).\n"
                "2. One or two easy, natural sentences on why it's the funniest — casual and conversational, not stiff."
            )},
        ],
        max_tokens = 200,
    )
    return(response["choices"][0]["message"]["content"])

def load_cards():
    with open(CARDS_JSON_PATH) as f:
        cards = json.load(f)
        white_cards=cards["white"]
        black_cards = cards["black"]
    return white_cards, black_cards

def get_black_card():
    _,black_cards = load_cards()
    random_card = random.choice(black_cards)
    return random_card["text"], random_card["pick"]

def process_text(text):
    white_cards,_ = load_cards()
    # lopp through white cards and lowercase them
    lowercase_cards = []
    for x in white_cards:
        lowercase_cards.append(x.lower())
    # lowercase the input text, that was deteted from the card
    text = text.lower()
    text = ' '.join(text.split()) #remove extra empty spaces etc

    # WRatio (the default scorer) blends in partial-ratio matching, which ties many
    # unrelated cards at a high score for short/noisy OCR text; plain ratio doesn't.
    result = fuzz.process.extractOne(text, lowercase_cards, scorer=fuzz.fuzz.ratio) # find matching card
    print("text_process result: ", result)
    return result


def main():
    print("Write player amount, only numbers:")
    player_amount = int(input())

    cam = cv2.VideoCapture(1) # open camera

    while True: # the whole program loop
        key = cv2.waitKey(1)
        if key == ord('q'):
            break
        black_card_text, pick_number = get_black_card() # get the black card
        print("Black card is: ", black_card_text)
        speak(f"Black card is {black_card_text}")
        cards = [] # all the player's cards for this round
        player = 0
        while player < player_amount: # loop for program adding cards for that turn
            pick = 0
            player_cards = [] # one player's cards for that tunr
            while pick < pick_number: # loop one player's cards for as times as black card requires
                instructions = [
                    f"Player {player + 1}/{player_amount} - card {pick + 1}/{pick_number}",
                    "Show the card and press 'c' to detect",
                    f"Black card is: {black_card_text}"
                ]
                card_result = detect_card(cam, instructions)
                if card_result is None:
                    continue
                elif card_result == ERROR_MSG:
                    print(ERROR_MSG)
                else:
                    player_cards.append(card_result)
                    pick += 1
            cards.append(player_cards)
            player += 1

        # run llama chat in the background so the camera window stays responsive
        result = {}
        def run_llama_chat():
            result["response"] = llama_chat(black_card=black_card_text, pick_number=pick_number, player_cards=cards)
        thread = threading.Thread(target=run_llama_chat, daemon=True)
        thread.start()

        while thread.is_alive():
            ret, frame = cam.read()
            draw_instructions(frame, ["Thinking... choosing the funniest card(s)"])
            cv2.imshow(WINDOW_NAME, frame)
            cv2.waitKey(1)

        response = result["response"]
        print("llama response: ", response)
        speak(response)

        while True: # show the result until a key is pressed
            ret, frame = cam.read()
            draw_instructions(frame, [response, "Press any key to continue..."])
            cv2.imshow(WINDOW_NAME, frame)
            if cv2.waitKey(1) != -1:
                break

    cam.release()
    cv2.destroyAllWindows()

if __name__=="__main__":
    main()