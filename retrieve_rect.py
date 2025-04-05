#!/usr/bin/env python3
# Pressure Advance Camera calibration for Klipper
#
# Copyright (C) 2025 Marius Wachtler <undingen@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import cv2
import matplotlib.pyplot as plt
import numpy as np


class RetrieveRect:
    def __init__(self, debug=False):
        """
        Initialize the RetrieveRect class.
        """
        self.debug = debug

    def process_image(self, image):
        """
        Process the image to extract and correct the rectangle.
        """
        # Create a copy of the image
        img = image.copy()

        if img.shape[2] == 4:
            # img = img[:, :, :3]
            mask = np.any(img > 0, axis=2)
        else:
            raise ValueError("Image must have an alpha channel")

        # Convert mask to binary image
        mask = mask.astype(np.uint8) * 255

        # Clean up the mask to remove thin artifacts
        mask = self._clean_mask(mask)

        # Find corners of the rectangle
        corners = self._detect_corners(mask)

        if corners is None or len(corners) != 4:
            raise ValueError("Could not detect exactly 4 corners of rectangle")

        # Order corners consistently (top-left, top-right, bottom-right, bottom-left)
        ordered_corners = self._order_corners(corners)

        # Correct perspective distortion
        corrected_img = self._correct_perspective(img, ordered_corners)

        # Display debug info if requested
        if self.debug:
            self._display_debug_info(img, mask, ordered_corners, corrected_img)

        return corrected_img

    def _clean_mask(self, mask):
        """
        Clean the mask to remove thin artifacts.
        """
        # Apply morphological operations to remove thin lines
        kernel = np.ones((5, 5), np.uint8)

        # Opening operation (erosion followed by dilation)
        # This removes small objects and thin lines
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=4)

        # Close any small holes in the rectangle
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=4)

        return mask

    def _detect_corners(self, mask):
        """
        Detect the four corners of the rectangle in the binary mask.
        """
        # Find contours in the mask
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None

        # Filter contours by area to ignore small artifacts
        min_area = 1000
        valid_contours = [cnt for cnt in contours if cv2.contourArea(cnt) > min_area]

        if not valid_contours:
            return None

        # Find the largest contour
        largest_contour = max(valid_contours, key=cv2.contourArea)

        for scale in [0.01, 0.02, 0.03, 0.05, 0.07, 0.1]:
            # Approximate the contour to get the corners
            epsilon = scale * cv2.arcLength(largest_contour, True)
            corners = cv2.approxPolyDP(largest_contour, epsilon, True)
            if len(corners) == 4:
                if self.debug:
                    print(f"Found 4 corners using {scale} for corner detection")
                break

        # If we still don't have exactly 4 corners, use minimum area rectangle
        if len(corners) != 4:
            if self.debug:
                print(f"Did not find 4 corners, using minAreaRect")
            rect = cv2.minAreaRect(largest_contour)
            box = cv2.boxPoints(rect)
            corners = np.int0(box)

        return corners.reshape(-1, 2)

    def _order_corners(self, corners):
        """
        Order the corners: top-left, top-right, bottom-right, bottom-left.
        """
        # Sort corners by y-coordinate (ascending)
        sorted_by_y = corners[np.argsort(corners[:, 1]), :]
        # The first two are the top corners, the last two are the bottom corners
        top_two = sorted_by_y[:2]
        bottom_two = sorted_by_y[2:]

        # Sort the top corners by x-coordinate to get top-left and top-right
        top_left, top_right = top_two[np.argsort(top_two[:, 0]), :]
        # Sort the bottom corners by x-coordinate to get bottom-left and bottom-right
        bottom_left, bottom_right = bottom_two[np.argsort(bottom_two[:, 0]), :]

        return np.array(
            [top_left, top_right, bottom_right, bottom_left], dtype="float32"
        )

    def _correct_perspective(self, image, corners):
        """
        Correct the perspective distortion using the detected corners.
        """
        # Calculate width and height for the new image
        width_a = np.sqrt(
            ((corners[0][0] - corners[1][0]) ** 2)
            + ((corners[0][1] - corners[1][1]) ** 2)
        )
        width_b = np.sqrt(
            ((corners[3][0] - corners[2][0]) ** 2)
            + ((corners[3][1] - corners[2][1]) ** 2)
        )
        max_width = max(int(width_a), int(width_b))

        height_a = np.sqrt(
            ((corners[0][0] - corners[3][0]) ** 2)
            + ((corners[0][1] - corners[3][1]) ** 2)
        )
        height_b = np.sqrt(
            ((corners[1][0] - corners[2][0]) ** 2)
            + ((corners[1][1] - corners[2][1]) ** 2)
        )
        max_height = max(int(height_a), int(height_b))

        # Set destination dimensions
        dst_width = max_width
        dst_height = max_height

        # Define destination points for perspective transform
        dst_points = np.array(
            [
                [0, 0],  # Top-left
                [dst_width - 1, 0],  # Top-right
                [dst_width - 1, dst_height - 1],  # Bottom-right
                [0, dst_height - 1],  # Bottom-left
            ],
            dtype="float32",
        )

        # Convert corners to float32
        corners = corners.astype("float32")

        # Calculate the perspective transform matrix
        perspective_matrix = cv2.getPerspectiveTransform(corners, dst_points)

        # Apply the perspective transformation
        corrected_img = cv2.warpPerspective(
            image, perspective_matrix, (dst_width, dst_height)
        )

        # Removed rotation step so output orientation matches the input image.
        return corrected_img

    def _display_debug_info(self, original_img, mask, corners, corrected_img):
        """
        Display debug information about the processing steps.
        """
        # Create a figure with 2x2 subplots
        fig, (axs1, axs2) = plt.subplots(2, 2, figsize=(10, 20))

        # Display the original image
        assert original_img.shape[2] == 4
        rgb_img = cv2.cvtColor(original_img[:, :, :3], cv2.COLOR_BGR2RGB)
        axs1[0].imshow(rgb_img)
        axs1[0].set_title("Original Image")

        # Display the mask with detected corners
        debug_img = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)

        # Draw corners on the debug image with labels
        corner_labels = ["Top-Left", "Top-Right", "Bottom-Right", "Bottom-Left"]
        corner_colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]

        for i, (corner, label, color) in enumerate(
            zip(corners, corner_labels, corner_colors)
        ):
            cv2.circle(debug_img, tuple(corner.astype(int)), 10, color, -1)
            pt = corner.astype(int)
            offset = [-50, -50] if pt[1] < original_img.shape[0] / 2 else [-50, 50]
            text_position = tuple(pt + offset)
            cv2.putText(
                debug_img,
                f"{i+1}: {label}",
                text_position,
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                color,
                2,
            )

        # Draw contour outline
        for i in range(4):
            pt1 = tuple(corners[i].astype(int))
            pt2 = tuple(corners[(i + 1) % 4].astype(int))
            cv2.line(debug_img, pt1, pt2, (0, 255, 0), 2)

        axs1[1].imshow(debug_img)
        axs1[1].set_title("Detected Rectangle")

        # Display the corrected image
        assert corrected_img.shape[2] == 4
        rgb_corrected = cv2.cvtColor(corrected_img[:, :, :3], cv2.COLOR_BGR2RGB)
        axs2[0].imshow(rgb_corrected)
        axs2[0].set_title("Corrected Rectangle")

        # Display the corrected images alpha channel
        axs2[1].imshow(corrected_img[:, :, 3])
        axs2[1].set_title("Corrected Rectangle Alpha")

        # Remove axis ticks
        from itertools import chain

        for ax in chain(axs1, axs2):
            ax.set_xticks([])
            ax.set_yticks([])

        plt.tight_layout()
        plt.show()
