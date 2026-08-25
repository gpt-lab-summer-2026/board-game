import cv2
import numpy as np
import pytesseract

FONT = cv2.FONT_HERSHEY_COMPLEX
WINDOW_NAME = "Card Game"

def order_points(pts):
    # Order 4 corner points as: top-left, top-right, bottom-right, bottom-left
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect


def four_point_transform(image, pts):
    rect = order_points(pts)
    (tl, tr, br, bl) = rect
    max_width = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    max_height = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    dst = np.array([
        [0, 0],
        [max_width - 1, 0],
        [max_width - 1, max_height - 1],
        [0, max_height - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (max_width, max_height))


def find_card_contour(candidates, frame_shape, border_margin=5):
    # Try each candidate contour (largest first), increasing epsilon until
    # it collapses to a quadrilateral that isn't just the frame edge
    height, width = frame_shape[:2]
    for c in candidates:
        peri = cv2.arcLength(c, True)
        for eps in np.linspace(0.01, 0.05, 10):
            approx = cv2.approxPolyDP(c, eps * peri, True)
            if len(approx) != 4:
                continue
            x, y, w, h = cv2.boundingRect(approx)
            touches_border = (
                x <= border_margin
                or y <= border_margin
                or x + w >= width - border_margin
                or y + h >= height - border_margin
            )
            if touches_border:
                continue
            return approx
    return None


def crop_card_footer(card, footer_ratio=0.15):
    # crop off the bottom branding strip ("Cards Against Humanity" logo/text)
    height = card.shape[0]
    return card[: int(height * (1 - footer_ratio)), :]


def binarize_for_ocr(card):
    gray = cv2.cvtColor(card, cv2.COLOR_BGR2GRAY)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # CAH cards are either black-with-white-text or white-with-black-text;
    # Tesseract wants dark text on a light background, so invert dark cards
    if np.mean(gray) < 128:
        binary = cv2.bitwise_not(binary)
    # pad with a white border so text near the card edge isn't clipped
    return cv2.copyMakeBorder(binary, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)


def detect_text(frame):
    display = frame.copy()

    # preprocess
    frame_gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(frame_gray, (5,5), 0)
    canny = cv2.Canny(blurred, 50 ,150)
    morph = cv2.morphologyEx(canny, cv2.MORPH_CLOSE, np.ones((5,5),np.uint8))
    cv2.imshow(WINDOW_NAME, morph)
    cv2.waitKey(1000)

    # Find contours
    contours, _ = cv2.findContours(morph.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # sort contours
    sorted_cnts = sorted(contours, key=cv2.contourArea, reverse=True)
    sorted_10 = sorted_cnts[0:10]
    approx = find_card_contour(sorted_10, frame.shape)

    if approx is None:
        print("Could not find a 4-point card contour")
        return

    cv2.drawContours(display, [approx], -1, (0, 255, 0), 3)
    cv2.imshow(WINDOW_NAME, display)
    cv2.waitKey(1000)
    # processing card for text detection
    card = four_point_transform(frame, approx.reshape(4, 2))
    cropped = crop_card_footer(card)
    ocr_image = binarize_for_ocr(cropped)

    text = pytesseract.image_to_string(ocr_image, config="--psm 6")
    print("Pytesseract extracted text: ", text)
    return text
