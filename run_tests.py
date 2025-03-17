#!/usr/bin/env python3
import os
import sys
import re

from pa_calib2 import detect_best_line  # Adjust import as needed

def main():
    failing_tests = []
    num_passed_tests = 0
    pattern = re.compile(r'_(\d+(?:,\d+)*)\.jpg$', re.IGNORECASE)
    for root, _, files in os.walk("data"):
        for file in files:
            if file.lower().endswith(".jpg"):
                path = os.path.join(root, file)
                m = pattern.search(file)
                if not m:
                    print(f"Skipping {path}: filename pattern not matched")
                    continue
                expected_values = [int(val) for val in m.group(1).split(',')]
                result, _ = detect_best_line(path, debug=False)
                if result in expected_values:
                    #print(f"PASS: {path} Expected one of {expected_values}, Got: {result}")
                    num_passed_tests += 1
                else:
                    print(f"FAIL: {path} Expected one of {expected_values}, Got: {result}")
                    failing_tests.append(f"{path} (Expected one of {expected_values}, Got: {result})")

    print("\nSummary:")
    print(f"Num tests passed: {num_passed_tests}")
    print(f"Num tests failed: {len(failing_tests)}")
    if failing_tests:
        print("\nFailed tests:")
        for fail in failing_tests:
            print(fail)
    sys.exit(1 if failing_tests else 0)

if __name__ == "__main__":
    main()
