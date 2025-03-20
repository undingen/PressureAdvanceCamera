#!/usr/bin/env python3
# Pressure Advance Camera calibration for Klipper
#
# Copyright (C) 2025 Marius Wachtler <undingen@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import cv2
import numpy as np
import matplotlib.pyplot as plt
import sys

class LineAnalyzer:
    def __init__(self, image, min_blob_area=100, gap_penalty=1000, debug=False):
        self.min_blob_area = min_blob_area
        self.gap_penalty = gap_penalty
        self.debug = debug
        self.image = image
        self.mask = None
        self.contours = []
        self.lines = []
        self.problematic_regions = []
        
        self._process_image()
        self._find_contours()
        self._group_contours_into_lines()
        self._compute_thickness_profiles()
        self._determine_problematic_regions()
        self._compute_smoothness_metrics()
        
        if self.debug:
            self._debug_output()

    def _process_image(self):
        # Crop 50 pixels from each side to remove rectangle border
        img = self.image[50:-50, 50:-50]
        
        if img.shape[2] == 4: # RGBA
            alpha = img[:, :, 3]
            self.mask = (alpha > 0).astype(np.uint8) * 255
            self.image = cv2.cvtColor(img, cv2.COLOR_BGRA2RGB)
        else:
            raise ValueError("Image must have an alpha channel")

            self.mask = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, self.mask = cv2.threshold(self.mask, 1, 255, cv2.THRESH_BINARY)
            self.image = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        self.mask = self._clean_mask(self.mask)

    def _clean_mask(self, mask):
        """
        Clean the mask to remove thin artifacts.
        """
        # Apply morphological operations to remove thin lines
        kernel = np.ones((5, 5), np.uint8)
        
        # Opening operation (erosion followed by dilation)
        # This removes small objects and thin lines
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=2)
        
        # Close any small holes in the rectangle
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        
        return mask

    def _find_contours(self):
        contours, _ = cv2.findContours(self.mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        self.contours = [c for c in contours if cv2.contourArea(c) >= self.min_blob_area]

    def _group_contours_into_lines(self):
        if not self.contours:
            return
        
        centroids = []
        for c in self.contours:
            M = cv2.moments(c)
            cy = M['m01']/M['m00'] if M['m00'] else c[0][0][1]
            centroids.append(cy)
        
        sorted_contours = sorted(zip(self.contours, centroids), key=lambda x: x[1])
        lines = []
        current_line = []
        y_threshold = self.image.shape[0] * 0.02
        
        for c, cy in sorted_contours:
            if current_line and abs(cy - current_line[-1][1]) > y_threshold:
                lines.append([cnt for cnt, _ in current_line])
                current_line = []
            current_line.append((c, cy))
        if current_line:
            lines.append([cnt for cnt, _ in current_line])
        
        self.lines = lines[::-1]

    def _compute_thickness_profiles(self):
        h, w = self.mask.shape
        for line_idx in range(len(self.lines)):
            thickness = np.zeros(w)
            line_contours = self.lines[line_idx]
            
            combined_mask = np.zeros((h, w), dtype=np.uint8)
            for cnt in line_contours:
                cv2.drawContours(combined_mask, [cnt], -1, 255, -1)
            
            for x in range(w):
                column = combined_mask[:, x]
                y_coords = np.where(column > 0)[0]
                if y_coords.size > 0:
                    thickness[x] = y_coords.ptp() + 1
            
            self.lines[line_idx] = (line_contours, thickness)

    def _determine_problematic_regions(self):
        """
        Splits the image vertically into left and right halves. 
        For each half, it scans each column (x position) and computes the standard deviation 
        of thickness values from all lines at that column. The x position with the highest 
        standard deviation in each half is considered the problematic area. A region around 
        that x position (expanded by region_size) is then marked as problematic.
        """
        w = self.mask.shape[1]
        region_size = int(w * 0.1)
        problematic_regions = []
        for half in [slice(0, w//2), slice(w//2, w)]:
            max_std = 0
            peak = None
            for x in range(half.start, half.stop):
                values = []
                for line in self.lines:
                    thickness = line[1]
                    values.append(thickness[x])
                if values:
                    column_std = np.std(values)
                    if column_std > max_std:
                        max_std = column_std
                        peak = x
            if peak is not None:
                start = max(half.start, peak - region_size)
                end = min(half.stop, peak + region_size)
                problematic_regions.append((start, end))
        self.problematic_regions = problematic_regions[:2]

    def _compute_smoothness_metrics(self):
        for line_idx in range(len(self.lines)):
            _, thickness = self.lines[line_idx]
            
            valid = thickness[thickness > 0]
            std = np.std(valid) if len(valid) > 1 else 0
            gaps = np.sum(thickness == 0)
            s1 = std + gaps * self.gap_penalty
            
            s2 = 0
            for start, end in self.problematic_regions:
                section = thickness[start:end+1]
                section_std = np.std(section[section > 0]) if np.any(section > 0) else 0
                section_gaps = np.sum(section == 0)
                s2 += section_std + section_gaps * self.gap_penalty
            
            self.lines[line_idx] = (*self.lines[line_idx], s1, s2)

    def get_smoothest_lines(self, top=5):
        #sorted_lines = sorted(enumerate(self.lines), key=lambda x: x[1][2])  # Sort by metric over total line
        sorted_lines = sorted(enumerate(self.lines), key=lambda x: x[1][3])  # Sort by metric focusing on problematic areas
        return [(i+1, line_data[2], line_data[3]) for i, line_data in sorted_lines[:top]]

    def _debug_output(self):
        plt.figure(figsize=(15, 10))
        plt.imshow(self.image)
        
        top_lines = self.get_smoothest_lines(5)
        colors = plt.cm.viridis(np.linspace(0, 1, len(top_lines)))
        
        # Draw contours for each line
        for (line_num, s1, s2), color in zip(top_lines, colors):
            contours, *_ = self.lines[line_num-1]
            for cnt in contours:
                # Draw each contour with a unique color per line
                plt.plot(cnt[:, 0, 0], cnt[:, 0, 1], color=color, linewidth=2)
            
            # Add a label point
            x, y, w, h = cv2.boundingRect(contours[0])
            # Position label to the right of the bounding rectangle
            plt.text(x+w+15, y+h, f'Line {line_num} (S1:{s1:.1f}, S2:{s2:.1f})', 
                     color=color, fontsize=9, backgroundcolor='white')
        
        # Add rectangles for problematic regions
        for start, end in self.problematic_regions:
            plt.axvspan(start, end, color='red', alpha=0.2)
        
        plt.title("Lines with Contours")
        plt.tight_layout()
        
        plt.figure(figsize=(12, 6))
        
        for (line_num, s1, s2), color in zip(top_lines, colors):
            _, thickness, *_ = self.lines[line_num-1]
            plt.plot(thickness, color=color, alpha=0.7,
                    label=f'Line {line_num}\nS1: {s1:.1f}\nS2: {s2:.1f}')
        
        for start, end in self.problematic_regions:
            plt.axvspan(start, end, color='red', alpha=0.2)
        
        plt.xlabel("X Position")
        plt.ylabel("Thickness")
        plt.legend(bbox_to_anchor=(1.05, 1), loc='upper left')
        plt.tight_layout()
        plt.show()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 line_analyzer.py <image_path>")
        sys.exit(1)
    
    img = cv2.imread(sys.argv[1], cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError("Image not found")
    analyzer = LineAnalyzer(img, debug=True)
    smoothest = analyzer.get_smoothest_lines()
    print("Top 5 smoothest lines:", smoothest)
