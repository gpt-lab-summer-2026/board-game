import cv2
import textwrap

from text_detection import *
from config import *
from main import process_text

def draw_instructions(frame, lines):
    wrapped = []
    for line in lines:
        wrapped.extend(textwrap.wrap(line, width=80) or [""])
    for i, line in enumerate(wrapped):
        y = 30 + i * 30
        cv2.putText(frame, line, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (54, 207, 48), 2)

def detect_card(cam, instructions):
    # Open the default camera
    ret, frame = cam.read()
    display = frame.copy()
    draw_instructions(display, instructions)
    cv2.imshow(WINDOW_NAME, display)

    key = cv2.waitKey(1)

    label = None
    if key == ord('c'):
        card_text = detect_text(frame=frame)
        if card_text is None:
            label = ERROR_MSG
        else:
            matched_text, score, _ = process_text(card_text)
            label = matched_text if score > 70 else ERROR_MSG
        result_frame = frame.copy()
        draw_instructions(result_frame, instructions + [f"The detected text was: {label}", "Press 'r' to redo, or any other key to accept"])
        cv2.imshow(WINDOW_NAME, result_frame)
        if cv2.waitKey(0) == ord('r'):
            return None
    return label