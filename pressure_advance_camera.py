# Pressure Advance Camera calibration for Klipper
#
# Copyright (C) 2025 Marius Wachtler <undingen@gmail.com>
#
# This file may be distributed under the terms of the GNU GPLv3 license.

import math
import os
import re
import subprocess

"""
Default Configuration:

[pressure_advance_camera]
camera_offset_x:        # X offset from nozzle to camera, negative is left of nozzle
camera_offset_y:        # Y offset from nozzle to camera, negative is infront of nozzle
photo_height:           # Height in mm to position the nozzle for photo - for my cam 5-6cm

script_path: ~/PressureAdvanceCamera/pa_calibrate.py
#camera_id: 0           # OpenCV Camera ID or crowsnest url
camera_id: "http://localhost/webcam/?action=snapshot"
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
bed_mash:               # Name of the bed mesh to load, e.g. "default"
"""


class PressureAdvanceCamera:
    def __init__(self, config):
        self.name = config.get_name().split()[-1]
        self.printer = config.get_printer()
        self.gcode = self.printer.lookup_object("gcode")

        self.script_path = config.get(
            "script_path", "~/PressureAdvanceCamera/pa_calibrate.py"
        )
        self.script_path = os.path.expanduser(self.script_path)
        if not os.path.exists(self.script_path):
            raise config.error(f"Script {self.script_path} not found")

        # Configuration parameters
        self.timeout = config.getfloat("timeout", 60.0 * 10, above=0.0)
        self.camera_id = config.get(
            "camera_id", "http://localhost/webcam/?action=snapshot"
        )
        self.camera_offset_x = config.getfloat("camera_offset_x")
        self.camera_offset_y = config.getfloat("camera_offset_y")
        self.photo_height = config.getfloat("photo_height")

        # Default test pattern parameters
        self.x_start = config.getfloat("x_start", 2.0, above=0.0)
        self.y_start = config.getfloat("y_start", 2.0, above=0.0)
        self.width = config.getfloat("width", 40.0, above=20.0)
        self.pa_start = config.getfloat("pa_start", 0.0, minval=0.0)
        self.pa_end = config.getfloat("pa_end", 0.1, above=0.0)
        self.pa_step = config.getfloat("pa_step", 0.005, above=0.0)
        self.line_spacing = config.getfloat("line_spacing", 3, above=2.5)
        self.hotend_temperature = config.getfloat("hotend_temp", 200.0, minval=0.0)
        self.bed_temperature = config.getfloat("bed_temp", 60.0, minval=0.0)
        self.speed = config.getfloat("speed", 100.0, minval=0.0)
        self.bed_mesh = config.get("bed_mesh", "")

        # Process handling
        self.proc_fd = None
        self.partial_output = ""
        self.full_output = ""

        # Save test pattern params used in the last run for later analysis
        self.last_pattern_params = {}

        # Register commands
        self.gcode.register_command(
            "SET_PRESSURE_ADVANCE_CAMERA",
            self.cmd_SET_PRESSURE_ADVANCE_CAMERA,
            desc=self.cmd_SET_PRESSURE_ADVANCE_CAMERA_help,
        )
        self.gcode.register_command(
            "DRAW_PRESSURE_ADVANCE_PATTERN",
            self.cmd_DRAW_PRESSURE_ADVANCE_PATTERN,
            desc=self.cmd_DRAW_PRESSURE_ADVANCE_PATTERN_help,
        )

    def _process_output(self, eventime):
        if self.proc_fd is None:
            return
        try:
            data = os.read(self.proc_fd, 4096)
        except Exception:
            return
        data = self.partial_output + data.decode()
        self.full_output += data

        if "\n" not in data:
            self.partial_output = data
            return
        elif data[-1] != "\n":
            split = data.rfind("\n") + 1
            self.partial_output = data[split:]
            data = data[:split]
        else:
            self.partial_output = ""
        self.gcode.respond_info(data)

    cmd_DRAW_PRESSURE_ADVANCE_PATTERN_help = "Draw a pressure advance test pattern"

    def cmd_DRAW_PRESSURE_ADVANCE_PATTERN(self, gcmd):
        # Parse parameters
        x_start = gcmd.get_float("X_START", self.x_start)
        y_start = gcmd.get_float("Y_START", self.y_start)
        width = gcmd.get_float("WIDTH", self.width)
        pa_start = gcmd.get_float("PA_START", self.pa_start)
        pa_end = gcmd.get_float("PA_END", self.pa_end)
        pa_step = gcmd.get_float("PA_STEP", self.pa_step)
        line_spacing = gcmd.get_float("LINE_SPACING", self.line_spacing)
        speed = gcmd.get_float("SPEED", self.speed)
        extrusion_multiplier = gcmd.get_float("EXTRUSION_MULTIPLIER", 1.0)
        temperature = gcmd.get_float("HOTEND_TEMP", self.hotend_temperature)
        bed_temperature = gcmd.get_float("BED_TEMP", self.bed_temperature)
        filament_diameter = gcmd.get_float("FILAMENT_DIAMETER", 1.75)
        nozzle_diameter = gcmd.get_float("NOZZLE_DIAMETER", 0.4)
        bed_mash = gcmd.get("BED_MASH", self.bed_mesh)

        # Parameter validation
        if pa_start >= pa_end:
            raise gcmd.error("PA_START must be less than PA_END")
        if pa_step <= 0:
            raise gcmd.error("PA_STEP must be positive")
        if width <= 0:
            raise gcmd.error("WIDTH must be positive")
        if line_spacing <= 0:
            raise gcmd.error("LINE_SPACING must be positive")

        # Calculate number of lines based on PA range and step
        num_lines = int((pa_end - pa_start) / pa_step) + 1
        assert num_lines >= 2, "Not enough lines for a meaningful test"

        # Calculate pattern height based on number of lines and spacing (double the spacing for top and bottom)
        height = (num_lines + 1 + 2) * line_spacing

        # Save parameters for later analysis
        self.last_pattern_params["pa_start"] = pa_start
        self.last_pattern_params["pa_end"] = pa_end
        self.last_pattern_params["num_lines"] = num_lines
        self.last_pattern_params["x_start"] = x_start
        self.last_pattern_params["y_start"] = y_start
        self.last_pattern_params["width"] = width
        self.last_pattern_params["height"] = height

        # Generate the G-code for the test pattern
        gcmd.respond_info(
            f"Generating pressure advance test pattern with {num_lines} lines"
        )
        gcmd.respond_info(f"Pattern dimensions: {width}mm x {height}mm")

        # Start with standard priming and setup
        gcode = []
        gcode.append("; Pressure Advance Test Pattern")
        gcode.append("G21 ; Set units to millimeters")
        gcode.append("G90 ; Use absolute positioning")
        gcode.append("M83 ; Use relative extrusion")

        # Set bed temperature but continue execution
        gcode.append(
            f"SET_HEATER_TEMPERATURE heater=heater_bed target={bed_temperature} ; Set final bed temp"
        )

        # Set temporary nozzle temperature to prevent oozing during homing
        gcode.append(
            "SET_HEATER_TEMPERATURE heater=extruder target=150 ; Set temporary nozzle temp to prevent oozing during homing"
        )
        gcode.append("G4 S10 ; Allow partial nozzle warmup")

        # Home all axes
        gcode.append("G28 ; Home all axes")

        if bed_mash:
            # Load bed mash
            gcode.append(f"BED_MESH_PROFILE LOAD={bed_mash} ; Load bed mesh")

        # Move to a safe position
        gcode.append("G1 Z50 F240 ; Move Z up to safe height")
        gcode.append("G1 X0 Y0 F3000 ; Move to front corner")

        # Set final temperature
        gcode.append(
            f"SET_HEATER_TEMPERATURE heater=extruder target={temperature} ; Set final nozzle temp"
        )

        # Wait for nozzle temperature to stabilize
        gcode.append(f"TEMPERATURE_WAIT SENSOR=heater_bed MINIMUM={bed_temperature-3}")
        gcode.append(f"TEMPERATURE_WAIT SENSOR=extruder MINIMUM={temperature-3}")

        # Reset extruder
        gcode.append("G92 E0 ; Reset extruder")

        extrusion_width = round(nozzle_diameter * 1.2, 2)
        # layer height - klipper recommends about 75% of nozzle diameter
        extrusion_height = round(nozzle_diameter * 0.75, 2)

        # Move to start position
        gcode.append(f"G1 X{x_start} Y{y_start} F6000 ; Move to start position")
        gcode.append(f"G1 Z{extrusion_height} F1000 ; Move to printing height")

        # Calculate filament cross-sectional area
        filament_area = math.pi * (filament_diameter / 2) ** 2

        # Convert volume to length by dividing by filament cross-sectional area
        extrusion_rate = (
            extrusion_width * extrusion_height * extrusion_multiplier
        ) / filament_area

        # Calculate rectangle coordinates
        x_end = x_start + width
        y_end = y_start + height

        # Draw the rectangle outline (twice as thick)
        for offset in [0, extrusion_width]:
            gcode.append(
                f"G1 X{x_start + offset} Y{y_start + offset} F6000 ; Move to inner outline start"
            )
            gcode.append("G1 F1200 ; Set moderate speed for outline")

            # Bottom edge
            gcode.append(
                f"G1 X{x_end - offset} Y{y_start + offset} E{(width - 2*offset) * extrusion_rate} ; Inner bottom edge"
            )
            # Right edge
            gcode.append(
                f"G1 X{x_end - offset} Y{y_end - offset} E{(height - 2*offset) * extrusion_rate} ; Inner right edge"
            )
            # Top edge
            gcode.append(
                f"G1 X{x_start + offset} Y{y_end - offset} E{(width - 2*offset) * extrusion_rate} ; Inner top edge"
            )
            # Left edge
            gcode.append(
                f"G1 X{x_start + offset} Y{y_start + offset} E{(height - 2*offset) * extrusion_rate} ; Inner left edge"
            )

        # Draw test lines with slow-fast-slow pattern
        slow_speed = 10  # 10 mm/s for slow segments

        # Calculate segment lengths and extrusion amounts
        segment1_pct = 0.10  # First 10% at slow speed
        segment2_pct = 0.60  # Middle 60% at configured speed
        segment3_pct = 0.30  # Last 30% at slow speed

        line_length = width - (3 * extrusion_width)
        segment1_length = line_length * segment1_pct
        segment2_length = line_length * segment2_pct
        segment3_length = line_length * segment3_pct

        segment1_extrusion = segment1_length * extrusion_rate
        segment2_extrusion = segment2_length * extrusion_rate
        segment3_extrusion = segment3_length * extrusion_rate

        for i in range(num_lines):
            current_pa = pa_start + (i * pa_step)
            y_pos = y_start + (
                (i + 2) * line_spacing
            )  # +2 because we want a gap at the start

            # Move to line start
            gcode.append(f"G1 Z{extrusion_height+0.1} F1000 ; Small Z hop")
            gcode.append(
                f"G1 X{x_start+extrusion_width} Y{y_pos} F12000 ; Move to line start"
            )
            gcode.append(f"G1 Z{extrusion_height} F1000 ; Back to printing height")

            # Set pressure advance for this line
            gcode.append(
                f"SET_PRESSURE_ADVANCE ADVANCE={current_pa:.6f} ; Set PA for line {i}"
            )

            # Draw the test line in segments with different speeds
            # Segment 1: Slow
            x_pos1 = x_start + extrusion_width + segment1_length
            gcode.append(f"G1 F{slow_speed * 60} ; Set slow speed")
            gcode.append(
                f"G1 X{x_pos1:.3f} Y{y_pos} E{segment1_extrusion:.5f} ; Line {i}, slow start"
            )

            # Segment 2: Fast
            x_pos2 = x_pos1 + segment2_length
            gcode.append(f"G1 F{speed * 60} ; Set configured speed")
            gcode.append(
                f"G1 X{x_pos2:.3f} Y{y_pos} E{segment2_extrusion:.5f} ; Line {i}, fast middle"
            )

            # Segment 3: Slow
            x_pos3 = x_pos2 + segment3_length
            gcode.append(f"G1 F{slow_speed * 60} ; Set slow speed")
            gcode.append(
                f"G1 X{x_pos3} Y{y_pos} E{segment3_extrusion:.5f} ; Line {i}, slow end"
            )

        # Finish up
        gcode.append("G1 E-4 F480 ; Retract filament")

        gcode.append("M140 S0 ; turn off heatbed")
        gcode.append("M104 S0 ; turn off temperature")

        # move back to bottom right corner to wipe of some of the extra filament
        gcode.append(f"G1 X{x_end - extrusion_width} Y{y_start - extrusion_width}")

        gcode.append("G1 Z40 F1000 ; Move up")
        # gcode.append("G92 E0 ; Reset extruder")

        gcode.append("M107 ; turn off fan")

        # Execute the G-code
        self.gcode.run_script_from_command("\n".join(gcode))

        gcmd.respond_info("Pressure advance test pattern completed")

    cmd_SET_PRESSURE_ADVANCE_CAMERA_help = (
        "Analyze pressure advance using camera capture"
    )

    def cmd_SET_PRESSURE_ADVANCE_CAMERA(self, gcmd):
        # Parse parameters
        num_lines = gcmd.get_int("NUM_LINES", self.last_pattern_params["num_lines"])
        photo_height = gcmd.get_float("PHOTO_HEIGHT", self.photo_height)

        # Override camera offsets if provided in command
        camera_offset_x = gcmd.get_float("CAMERA_OFFSET_X", self.camera_offset_x)
        camera_offset_y = gcmd.get_float("CAMERA_OFFSET_Y", self.camera_offset_y)

        # Parameter validation
        if num_lines <= 0:
            raise gcmd.error("NUM_LINES must be positive")

        # Move extruder to center of pattern for photo
        if (
            "x_start" in self.last_pattern_params
            and "width" in self.last_pattern_params
            and "height" in self.last_pattern_params
        ):
            x_center = self.last_pattern_params["x_start"] + (
                self.last_pattern_params["width"] / 2
            )
            y_center = self.last_pattern_params["y_start"] + (
                self.last_pattern_params["height"] / 2
            )

            # Adjust position based on camera offset so the camera is centered over the pattern
            x_position = max(0, x_center - camera_offset_x)
            y_position = max(0, y_center - camera_offset_y)

            # Move to center position at photo height
            self.gcode.run_script_from_command(
                f"G1 X{x_position} Y{y_position} F6000 ; Move for camera centering"
            )
            gcmd.respond_info(
                f"Moved to photo position (X:{x_position}, Y:{y_position}, Z:{photo_height})"
            )
            gcmd.respond_info(
                f"Camera position (X:{x_center}, Y:{y_center}) - using offset (X:{camera_offset_x}, Y:{camera_offset_y})"
            )

        self.gcode.run_script_from_command(
            f"G1 Z{photo_height} F1000 ; Move to photo height"
        )

        # dummy wait to make sure moves are finished
        self.gcode.run_script_from_command("G4 P1000")

        reactor = self.printer.get_reactor()
        try:
            # Launch the process
            cmd = [self.script_path, str(self.camera_id), str(num_lines)]
            gcmd.respond_info(f"Running: '{cmd}'")
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except Exception:
            raise gcmd.error(f"Failed to execute {self.script_path}")

        # Set up output handling
        self.proc_fd = proc.stdout.fileno()
        self.full_output = ""
        self.partial_output = ""
        hdl = reactor.register_fd(self.proc_fd, self._process_output)

        # Wait for completion or timeout
        eventtime = reactor.monotonic()
        endtime = eventtime + self.timeout
        complete = False

        while eventtime < endtime:
            eventtime = reactor.pause(eventtime + 0.05)
            if proc.poll() is not None:
                complete = True
                break

        # Clean up
        if not complete:
            proc.terminate()
            gcmd.respond_info("Pressure advance calibration timed out")

        if self.partial_output:
            gcmd.respond_info(self.partial_output)
            self.partial_output = ""

        reactor.unregister_fd(hdl)
        self.proc_fd = None

        # Check if successful
        if not complete or proc.returncode != 0:
            gcmd.respond_info("Pressure advance calibration failed")
            return

        # Parse the output for "Best line: X"
        match = re.search(r"Best line:\s*(\d+)", self.full_output)
        if match:
            best_line = int(match.group(1))

            # Calculate the actual pressure advance value based on line number
            pa_start = self.last_pattern_params["pa_start"]
            pa_end = self.last_pattern_params["pa_end"]
            pattern_lines = self.last_pattern_params["num_lines"]

            pa_step = (pa_end - pa_start) / (pattern_lines - 1)
            best_pa = pa_start + ((best_line - 1) * pa_step)

            gcmd.respond_info(f"Best line: {best_line}")
            gcmd.respond_info(f"Best pressure advance value: {best_pa:.6f}")

            # Apply the new pressure advance value
            try:
                gcmd.respond_info(f"Setting pressure advance to {best_pa:.6f}")
                self.gcode.run_script_from_command(
                    f"SET_PRESSURE_ADVANCE ADVANCE={best_pa:.6f}"
                )
                gcmd.respond_info("Pressure advance successfully updated")
            except Exception as e:
                gcmd.respond_info(f"Error setting pressure advance: {str(e)}")
        else:
            gcmd.respond_info("Could not find best line number in output")


def load_config(config):
    return PressureAdvanceCamera(config)
