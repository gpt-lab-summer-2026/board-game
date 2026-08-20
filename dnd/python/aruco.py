import cv2
import numpy as np

DEFAULT_DICT ="DICT_APRILTAG_36H10"

# Built once, not per frame: the dictionary and detector are static config,
# not something that depends on the image.
_DICTIONARY = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)

_PARAMS = cv2.aruco.DetectorParameters()
# The default window sweep (3..23 step 10) assumes fairly even lighting. Under
# a projector, brightness varies a lot within one tag's footprint (a shadow
# or a bright patch of projected map), so a wider max window and finer step
# give the adaptive threshold more chance to separate the tag from whatever
# is being projected onto it.
_PARAMS.adaptiveThreshWinSizeMax = 53
_PARAMS.adaptiveThreshWinSizeStep = 6
# Sub-pixel corners are more stable when the tag's edges are partly degraded
# by projected content rather than clean black/white.
_PARAMS.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX

_DETECTOR = cv2.aruco.ArucoDetector(_DICTIONARY, _PARAMS)

def generate_tags():
    # create the dictionary for markers type
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    size_of_marker = 400  # size of marker.

    # generating IDs with for loop
    for marker_id in range(6):
        # generating the marker
        img = cv2.aruco.generateImageMarker(dictionary, marker_id, size_of_marker)

        print("Dimension of Marker: ", img.shape, " id: ", marker_id)
        # save/write the image
        cv2.imwrite("marker_image{}.png".format(marker_id), img)

    # display the image(marker) on windows
    cv2.imshow("Marker", img)
    cv2.waitKey(0)

# def detect_from_images():


def process_frame(image):
    # Detect ArUco markers in the image.
    corners, marker_ids, rejected = _DETECTOR.detectMarkers(image)

    if corners:
        # looping through detected markers and marker ids at same time.
        for corner, marker_id in zip(corners, marker_ids):
            # Draw the marker corners.
            cv2.polylines(
                image, [corner.astype(np.int32)], True, (0, 255, 255), 3, cv2.LINE_AA
            )

            # Get the top-right, top-left, bottom-right, and bottom-left corners of the marker.
            # change the shape of numpy array to 4 by 2
            corner = corner.reshape(4, 2)

            # change the type of numpy array values integers
            corner = corner.astype(int)

            # extracting the corner of marker
            top_right, top_left, bottom_right, bottom_left = corner

            # Write the marker ID on the image.
            cv2.putText(
                image, f"id: {marker_id[0]}", top_right, cv2.FONT_HERSHEY_PLAIN, 1.3, (255, 0, 255), 2
            )
    return image

def detect_aruco():
    cam = cv2.VideoCapture(0)

    while True:
        ret, frame = cam.read()
        processed_frame = process_frame(frame)
        cv2.imshow('Camera', processed_frame)
        # Press 'q' to exit the loop
        if cv2.waitKey(1) == ord('q'):
            break

    # Release the capture and writer objects
    cam.release()
    cv2.destroyAllWindows()

detect_aruco()