#!/usr/bin/env python3
# Pressure Advance Camera calibration for Klipper
#
# Copyright (C) 2025 Marius Wachtler <undingen@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import argparse
import os
import time

import cv2

from capture_frame import capture_frame
from line_analyzer import LineAnalyzer
from retrieve_rect import RetrieveRect
from segment_image import SegmentImage

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Capture a frame from a camera and find best line."
    )
    parser.add_argument(
        "camera_id", help="Camera ID (integer) or URL to capture the frame from"
    )
    parser.add_argument("num_lines", type=int, help="Number of lines in image")
    args = parser.parse_args()

    image_dir = "images"
    img_file = f"{image_dir}/{int(time.time())}.jpg"
    print(
        f"Capturing camera frame: camera_id: {args.camera_id}, num_lines: {args.num_lines}, output: {img_file}"
    )

    # Change working directory to the script directory
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    if not os.path.exists(image_dir):
        os.makedirs(image_dir)

    # Read the API token from a file
    try:
        import os

        with open("fal.key", "r") as key_file:
            os.environ["FAL_KEY"] = key_file.read().strip()
    except FileNotFoundError:
        print(
            "Error: API key file 'fal.key' not found. Please store your API key in this file."
        )
        exit(1)
    except Exception as e:
        print(f"Error reading the API key file: {e}")
        exit(1)

    # Capture the image from the camera - retry sometimes capturing fails
    captured_frame = False
    for _ in range(3):
        try:
            frame = capture_frame(args.camera_id)
            if frame is not None:
                cv2.imwrite(img_file, frame)
                print(f"Frame captured from camera and saved as {img_file}")
                captured_frame = True
                break
        except Exception as e:
            print("Error during capture. Retrying...")
            time.sleep(1)
    assert captured_frame, "Failed to capture frame"

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
