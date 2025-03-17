
# Pressure Advance Camera Calibration for Klipper

This project introduces a tool to automatically calibrate the **pressure advance** setting for FDM 3D printers running the **Klipper firmware** using a low cost USB (endoscope) **camera** 📸 and computer vision. Pressure advance is a key feature in Klipper that enhances print quality by fine-tuning extruder behavior during acceleration and deceleration. By leveraging a camera to analyze a test pattern before each print, this tool simplifies and automates the calibration process, saving time and effort for users.

Please watch this Video where I explain the project: 

[![YouTube Video](https://img.youtube.com/vi/LptiyxAR9nc/0.jpg)](https://youtu.be/LptiyxAR9nc)

## ⚠️ Disclaimer

🚧 Early development version - verify results manually. Not responsible for damage. Test in safe environment first.

## ✨ Features

- **Automated Calibration:** Prints and captures a test pattern with a camera and determines the optimal pressure advance value.
- **Affordable Hardware:** Uses a low-cost USB endoscope camera (around €6) for image capture.
- **Open Source:** Licensed under **GPL3** which allows even commercial use, welcoming community contributions and modifications.

## 🤖 How It Works

1. **Test Pattern Creation:**
   - At the start of a print, the printer draws a series of lines with varying pressure advance values.
2. **Image Capture:**
   - The camera moves to the center of the test pattern takes a picture of it.
3. **Image Analysis:**
   - The image is processed using the open BirefNet model via the fal.ai API, which removes the background (build-plate) - I hope to get rid of this step in the future and run a small local model instead but until now this is required.
   - We identify the rectangle drawn in the pattern and crop it and fix the horrible lens distortion the cheap camera introduces.
   - Afterwards we identify the smoothest and most continuous line using OpenCV Computer Vision algorithms.
4. **Calibration Application:**
   - The software sets the optimal pressure advance value, and the printer continues the print with this setting.

## Requirements

- **Camera:**
   - A **cheap USB endoscope camera** (approximately €5). Ensure it is **full HD** and has a **flexible cable** (they also sell a semi-solid one which likely cause problems). Theoretical a webcam could also work if it can focus on something about 10cm away. [Here](https://www.aliexpress.com/item/1005006521256206.html) is the one I bought.
- **Mounting:**
   - The camera must be securely mounted on the printhead, facing straight down. [Here](https://www.printables.com/model/1233276-8mm-endoscope-camera-mount-using-existing-bltouch) you can find the mount I use which reuses the existing BLTouch mount
- **free USB Port**
- **Klipper and ssh access**

## 🚀 Setup

### Hardware Setup

1. **Mount the Camera:**
   - Attach a USB endoscope camera to the printhead, facing straight down at the build plate.
   - A sample mount for the **Ender 3** using the BLTouch mount is provided here.
2. **Camera Orientation:**
   - Plug the camera into a phone first to verify orientation. Rotate it **90° to the left** so that the test pattern lines run from top to bottom in the captured image, maximizing the camera’s resolution.
3. **Lighting:**
   - Ensure adequate lighting with no significant glare or reflections on the build plate where the test pattern will be printed.
4. **Connect the Camera:**
   - Plug the camera into the printer’s USB port.

### Software Setup

To set up the software, follow these steps on the printer:

1. **Clone the Repository:**
   ```sh
   git clone https://github.com/undingen/PressureAdvanceCamera.git
   ```
2. **Navigate to the Project Directory:**
   ```sh
   cd PressureAdvanceCamera
   ```
3. **Add Your FAL API Key:**
   Create a file named `fal.key` and insert your API key from [fal.ai](https://fal.ai) (used to remove the background of the captured image):
   Make sure to never share this API key with anyone!
   ```sh
   echo "<FAL_KEY>" > fal.key
   ```
4. **Link to Klipper Extras:**
   Create a symbolic link to the Klipper extras directory to add the extension:
   ```sh
   ln -s `pwd`/pressure_advance_camera.py ../klipper/klippy/extras/
   ```
5. **Install Dependencies:**
   Install the `fal-client` package using pip:
   ```sh
   pip3 install fal-client
   ```

### Software Configuration

1. **Crowsnest Check:**
   - Ensure the camera is not being used by crowsnest to avoid conflicts. You may have to comment out the camera section.
2. **Update `printer.cfg`:**
   - Add the following section to your Klipper `printer.cfg` file and cheange the values:
     ```ini
     [pressure_advance_camera]
     camera_offset_x: -23    # X offset from nozzle to camera, negative is left of nozzle
     camera_offset_y: -20    # Y offset from nozzle to camera, negative is in front of nozzle
     photo_height: 50        # Height in mm to position the nozzle for photo. For my cam 5-6cm
     ```
   - If multiple cameras are connected, set the `camera_id` parameter to the appropriate OpenCV camera ID.
3. **Check that the extension:**
   - Check that klipper uses the extensions by executing `HELP` inside the console and looking for GCodes called `DRAW_PRESSURE_ADVANCE_PATTERN` or `SET_PRESSURE_ADVANCE_CAMERA`. If this does not show up make sure you created the symlink and the printer.cfg entry and restart Klipper.

### Default Configuration

The following parameters are pre-configured and only need adjustment if your setup differs from the default (and some like the temperture is best to overwrite directly in the GCode by passing it as argument):

```ini
[pressure_advance_camera]
camera_offset_x:        # X offset from nozzle to camera, negative is left of nozzle
camera_offset_y:        # Y offset from nozzle to camera, negative is infront of nozzle
photo_height:           # Height in mm to position the nozzle for photo - for my cam 5-6cm

script_path: ~/PressureAdvanceCamera/pa_calibrate.py
camera_id: 0            # OpenCV camera ID
x_start: 2              # where to start the pattern
y_start: 2              # where to start the pattern
pa_start: 0.0
pa_end: 0.1
pa_step: 0.005
hotend_temp: 200        # Hotend temperature
bed_temp: 60            # Bed temperature
line_spacing: 3
width: 40
timeout: 600
speed: 100              # Speed for the fast segments
```

### Slicer Settings
For now only tested with OrcaSlicer (but this could ofcourse also be directly done inside the Klipper macros):
- Create a copy of your printers profile but under **Machine start G-Code** prepend this:
```
DRAW_PRESSURE_ADVANCE_PATTERN HOTEND_TEMP=[nozzle_temperature] BED_TEMP=[bed_temperature]
SET_PRESSURE_ADVANCE_CAMERA
```
- Make a copy of you filament profile but **uncheck** "Enable pressure advance" (else the emitted GCode would overwrite auto configed value).

## Software Dependencies

- **fal.ai API Key:**
   - Required for image segmentation due to the challenges of detecting lines with poor lighting and low-quality cameras. The project uses a open **BirefNet model** hosted on fal.ai’s servers.
   - Costs are minimal (less than **$0.01 per frame/print**), and new users may receive $1 credit upon signing up at [fal.ai](https://fal.ai). *(Note: I have no affiliation with fal.ai and hope I can change the project in the future todo all computation localy.)*
- **Python Packages:**
   - Install `fal-client` as outlined in the installation steps (OpenCV, numpy and Matplotlib should already be installed).

## 🐉 Limitation

If the contrast between the build-plate and filament is poor — meaning if you as a human cannot reliably detect the best line from the camera image — the software will also fail. It's important to have enough light for the camera to take a good picture while also avoiding glare spots that obstruct the view.


## Support me

If you find this project useful please support me so that I can spend more time on this project:

  [!["Github Sponsor"](./res/github_sponsor.png)](https://github.com/sponsors/undingen)
  [![Patreon](./res//patreon.png)](https://www.patreon.com/bePatron?u=10741923)
  [!["Buy Me A Coffee"](https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png)](https://www.buymeacoffee.com/hiernichterfunden)

## 🌐 Data Collection for future local model

- All captured images are saved in a subdirectory called **`images`**.
- Users are encouraged to email me the images undingen+pa@gmail.com or upload the images to [this Issue](https://github.com/undingen/PressureAdvanceCamera/issues/1) (after ensuring no private information is included!). This data will help train a smaller, future model that can run directly on the printer. But for this to succeed a lot of different training examples are required...

## 📜 License

This project is licensed under the **GNU General Public License v3.0 (GPL3)**. This means it is free to use, modify, and distribute, but any modifications must also be shared under the same open-source license.

## 🤝 Contributions

This is an **early-stage project**, and contributions are warmly welcomed! Whether it’s code improvements, bug fixes, documentation updates, or simply feedback, your input is invaluable. Please feel free to open issues or submit pull requests on GitHub.

