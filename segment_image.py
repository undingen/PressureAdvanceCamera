# Pressure Advance Camera calibration for Klipper
#
# Copyright (C) 2025 Marius Wachtler <undingen@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import base64
import requests
import pathlib

import cv2
import fal_client

class SegmentImage:
    """Class to handle image segmentation using the fal-ai API"""
    
    def __init__(self):
        self.model_path = "fal-ai/birefnet/v2"
        
    def segment(self, image_path, resolution="2048x2048", refine_foreground=True):
        """Segment a single image and save the results"""

        assert resolution in ("2048x2048", "1024x1024")
        
        image_base64 = self._image_to_base64(image_path)
        result = fal_client.subscribe(
            self.model_path,
            arguments={
                "image_url": image_base64,
                "model": "High Resolutions",
                "operating_resolution": resolution,
                "output_format": "png",
                "refine_foreground": refine_foreground,
                "output_mask": True
            },
            with_logs=True,
            on_queue_update=self._on_queue_update,
        )
        return self._save_result(result, image_path)
    
    def _on_queue_update(self, update):
        """Handle progress updates from the API"""
        if isinstance(update, fal_client.InProgress):
            for log in update.logs:
                print(log["message"])
    
    def _image_to_base64(self, image_path):
        """Convert an image to base64 encoded string"""
        assert image_path.endswith('.jpg')
        with open(image_path, "rb") as image_file:
            encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
        return f"data:image/jpeg;base64,{encoded_string}"
    
    def _save_result(self, result, image_path):
        """Save resulting mask and processed image to the same directory as input"""
        image_path = pathlib.Path(image_path)
        base_filename = image_path.stem
        directory = image_path.parent

        for (tag, name) in (("mask_image", "mask"), ("image", "out")):
            if result.get(tag) and result[tag].get("url"):
                img_path = directory / f"{base_filename}_{name}.png"
                response = requests.get(result[tag]["url"])
                with open(img_path, "wb") as f:
                    f.write(response.content)
                if tag == "image":
                    img = cv2.imread(str(img_path))

        return img
