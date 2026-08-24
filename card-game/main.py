import cv2
import json
import rapidfuzz as fuzz

from text_detection import *

CARDS_JSON_PATH= "cah-cards-compact.json"

def load_cards():
    with open(CARDS_JSON_PATH) as f:
        cards = json.load(f)
        white_cards=cards["white"]
    return white_cards

def process_text(text):
    white_cards = load_cards()
    # lopp through white cards and lowercase them
    lowercase_cards = []
    for x in white_cards:
        lowercase_cards.append(x.lower())
    # lowercase the input text, that was deteted from the card
    text.lower()
    text = ' '.join(text.split()) #remove extra empty spaces etc

    result = fuzz.process.extractOne(text, lowercase_cards) # find matching card
    print("result: ", result)
    return result


def main():
    # Open the default camera
    cam = cv2.VideoCapture(1)

    while True:
        ret, frame = cam.read()
        cv2.imshow(WINDOW_NAME, frame)

        # Press 'q' to exit the loop
        key = cv2.waitKey(1)
        if key == ord('q'):
            break
        elif key == ord('c'):
            print("taking frame to procesing")
            card_text = detect_text(frame=frame)
            matched_text, score, _ =  process_text(card_text)

            label = matched_text if score > 70 else "Couldn't detect the text, try again!"
            cv2.putText(frame, label, (40, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 2)
            cv2.imshow(WINDOW_NAME, frame)
            cv2.waitKey(0)

    cam.release()
    cv2.destroyAllWindows()

if __name__=="__main__":
    main()