#!/usr/bin/env python3
# Pressure Advance Camera calibration for Klipper
#
# Copyright (C) 2025 Marius Wachtler <undingen@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import argparse
import os
import sys
import time

import cv2

from line_analyzer import LineAnalyzer
from retrieve_rect import RetrieveRect
from segment_image import SegmentImage


def capture_frame(camera_id, output_filename="frame.jpg", manual_exposure=None):
    cap = cv2.VideoCapture(camera_id, cv2.CAP_V4L2)

    # Set resolution to 1920x1080
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)

    # Set MJPEG format (if supported by your camera)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

    # Set exposure mode
    if manual_exposure:
        # found this on internet, not sure if it works but says one has to first set to auto and then to manual to reliable set it
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)  # auto mode
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 1)  # manual mode
        cap.set(cv2.CAP_PROP_EXPOSURE, manual_exposure)
    else:
        cap.set(cv2.CAP_PROP_AUTO_EXPOSURE, 3)  # auto mode
        cap.read()  # capture a dummy frame I fear the first frame has wrong exposure

    time.sleep(1)
    ret, frame = cap.read()

    if ret:
        # Flip the image horizontally and vertically
        frame = cv2.flip(frame, -1)
        frame = cv2.rotate(frame, cv2.ROTATE_90_COUNTERCLOCKWISE)
        cv2.imwrite(output_filename, frame)
        print(f"Frame captured and saved as {output_filename}")
    else:
        print("Failed to capture frame")

    cap.release()
    cv2.destroyAllWindows()

    return ret


def capture_frame_retry(camera_id, output_filename="frame.jpg", manual_exposure=None):
    # Retry capturing a frame up to 3 times
    for _ in range(3):
        ret = capture_frame(camera_id, output_filename, manual_exposure)
        if ret:
            return True
        time.sleep(1)
    return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Capture a frame from a camera and process it for pressure advance calibration"
    )
    parser.add_argument(
        "camera_id", type=int, help="Camera ID to capture the frame from"
    )
    parser.add_argument(
        "num_lines", type=int, nargs="?", help="Number of lines in image"
    )
    parser.add_argument(
        "--photos", type=str, help="Photo prefix (capture a series of photos and exit)"
    )
    args = parser.parse_args()

    image_dir = "images"
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    # Change working directory to the script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # If --photos is provided, perform a sequence of captures
    if args.photos:
        auto_img_file = f"{image_dir}/{args.photos}_auto.jpg"
        capture_frame_retry(args.camera_id, auto_img_file)  # auto exposure

        # Got via with "v4l2-ctl --all"
        min_exposure = 50
        max_exposure = 2000  # 10k but that's too long
        num_images = 25

        exposure_values = [
            min_exposure + i * ((max_exposure - min_exposure) / (num_images - 1))
            for i in range(num_images)
        ]
        for exp in exposure_values:
            exp_img_file = f"{image_dir}/{args.photos}_e{int(exp)}.jpg"
            capture_frame_retry(args.camera_id, exp_img_file, manual_exposure=exp)
            time.sleep(0.5)
        sys.exit(0)

    # The remaining processing requires a num_lines argument
    if args.num_lines is None:
        parser.error("the following argument is required: num_lines")

    print(
        f"Capturing camera frame: camera_id: {args.camera_id}, num_lines: {args.num_lines}"
    )
    img_file = f"{image_dir}/{int(time.time())}.jpg"

    # Read the API token from a file
    try:
        with open("fal.key", "r") as key_file:
            os.environ["FAL_KEY"] = key_file.read().strip()
    except FileNotFoundError:
        print(
            "Error: API key file 'fal.key' not found. Please store your API key in this file."
        )
        sys.exit(1)
    except Exception as e:
        print(f"Error reading the API key file: {e}")
        sys.exit(1)

    if not capture_frame_retry(args.camera_id, img_file):
        sys.exit("Failed to capture frame")

    debug = False

    print("Calling SegmentImage")
    segmenter = SegmentImage()
    seg_img = segmenter.segment(img_file)

    print("Calling RetrieveRect")
    retrieve_rect = RetrieveRect(debug=debug)
    rect_img = retrieve_rect.process_image(seg_img)

    print("Calling LineAnalyzer")
    analyzer = LineAnalyzer(rect_img, debug=debug)
    smoothest = analyzer.get_smoothest_lines()
    print("Top 5 smoothest lines:", smoothest)
    print(f"Best line: {smoothest[0][0]}")
