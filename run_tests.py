#!/usr/bin/env python3
# Pressure Advance Camera calibration for Klipper
#
# Copyright (C) 2025 Marius Wachtler <undingen@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import os
import sys
import re

import cv2

from retrieve_rect import RetrieveRect
from line_analyzer import LineAnalyzer

def get_best_line(image_path, debug = False):
    seg_img = cv2.imread(image_path.replace(".jpg", "_out.png"), cv2.IMREAD_UNCHANGED)

    # Disable segmenting the images via the API in the tests (because would cost something). 
    # Instead just use the prepared images 
    if seg_img is None and 0:
        from segment_image import SegmentImage
        segmenter = SegmentImage()
        seg_img = segmenter.segment(image_path)

    if seg_img is None:
        raise ValueError("Image not found")

    retrieve_rect = RetrieveRect(debug=debug)
    rect_img = retrieve_rect.process_image(seg_img)

    analyzer = LineAnalyzer(rect_img, debug=debug)
    smoothest = analyzer.get_smoothest_lines()

    return smoothest[0][0]

def main():
    failing_tests = []
    num_passed_tests = 0
    pattern = re.compile(r'_(\d+(?:,\d+)*)\.jpg$', re.IGNORECASE)
    for root, _, files in os.walk("test_data"):
        for file in files:
            if file.lower().endswith(".jpg"):
                path = os.path.join(root, file)
                m = pattern.search(file)
                if not m:
                    print(f"Skipping {path}: filename pattern not matched")
                    continue
                expected_values = [int(val) for val in m.group(1).split(',')]

                try:
                    result = get_best_line(path, debug=False)
                except Exception as e:
                    print(f"FAIL: {path} Exception: {e}")
                    failing_tests.append(f"{path} (Exception: {e})")
                    continue

                if result in expected_values:
                    #print(f"PASS: {path} Expected one of {expected_values}, Got: {result}")
                    num_passed_tests += 1
                else:
                    print(f"FAIL: {path} Expected one of {expected_values}, Got: {result}")
                    failing_tests.append(f"{path} (Expected one of {expected_values}, Got: {result})")

    if failing_tests:
        print()
    print("Summary:")
    print(f"Num tests passed: {num_passed_tests}")
    print(f"Num tests failed: {len(failing_tests)}")
    if failing_tests:
        print("\nFailed tests:")
        for fail in failing_tests:
            print(fail)
    sys.exit(1 if failing_tests else 0)

if __name__ == "__main__":
    main()
