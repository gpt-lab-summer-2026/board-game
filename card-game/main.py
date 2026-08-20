import cv2
import pytesseract
from matplotlib import pyplot as plt
from PIL import Image

image_path = "images/1.jpg"
image = cv2.imread(image_path)
cv2.imshow("tewst", image)
cv2.waitKey(0)

img2 = Image.open(image_path)
# preprocess
gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
cv2.imshow("gray", thresh)
cv2.waitKey(0)

text = pytesseract.image_to_string(thresh)
print("Extracted text: ", text)

data = pytesseract.image_to_data(thresh)
print(data[:200])