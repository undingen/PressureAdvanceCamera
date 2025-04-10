# Pressure Advance Camera calibration for Klipper
#
# Copyright (C) 2025 Marius Wachtler <undingen@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import time

import cv2
import numpy as np
import requests


# This script captures a frame from a camera, either via OpenCV (if its a digit - camera id) or a URL.
def capture_frame(camera_id_url):
    frame = None

    if camera_id_url.isdigit():  # If its just a number use opencv
        cap = cv2.VideoCapture(camera_id_url, cv2.CAP_V4L2)

        # Set resolution to 1920x1080
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

        # Set MJPEG format (if supported by your camera)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

        ret, frame = cap.read()
        if not ret:  # retry once
            time.sleep(1)
            ret, frame = cap.read()

        cap.release()
    else:  # Camera ID is a URL, use requests to fetch the image
        try:
            response = requests.get(camera_id_url, timeout=2)
            response.raise_for_status()
            img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
            frame = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        except requests.RequestException as e:
            print(f"Error capturing snapshot from URL: {e}")

    if frame is None:
        print(f"Failed to capture frame from camera '{camera_id_url}'")
        return False

    # Flip the image horizontally and vertically
    frame = cv2.flip(frame, -1)
    frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)

    return frame
