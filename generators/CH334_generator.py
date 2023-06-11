#!/usr/bin/env python3

import argparse
import logging
import multiprocessing
import os
import re
import sys
from itertools import repeat
from datetime import datetime
import csv


common = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, "common")
)
if common not in sys.path:
    sys.path.insert(0, common)

common = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir, "common")
)
if common not in sys.path:
    sys.path.insert(0, common)

import kicad_sym
from DrawingElements import Drawing, DrawingPin, DrawingRectangle, ElementFill
from Point import Point


class DataPin:
    _PIN_TYPES_MAPPING = {
        ""
        "Upstream": DrawingPin.PinElectricalType.EL_TYPE_BIDIR,
        "Downstream": DrawingPin.PinElectricalType.EL_TYPE_BIDIR,
        "Overcurrent": DrawingPin.PinElectricalType.EL_TYPE_OUTPUT,
        "Power": DrawingPin.PinElectricalType.EL_TYPE_POWER_INPUT,
        "Input": DrawingPin.PinElectricalType.EL_TYPE_INPUT,
        "Output": DrawingPin.PinElectricalType.EL_TYPE_OUTPUT,
        "InOut": DrawingPin.PinElectricalType.EL_TYPE_BIDIR,
        "Reset": DrawingPin.PinElectricalType.EL_TYPE_INPUT,
        "NC": DrawingPin.PinElectricalType.EL_TYPE_NC,
        "Clock": DrawingPin.PinElectricalType.EL_TYPE_INPUT,
    }

    def __init__(self, number, name, pintype):
        self.num = number
        self.name = name
        self.pintype = pintype
        self.altfuncs = []

    def to_drawing_pin(self, **kwargs):
        # Get the el_type for the DrawingPin
        el_type = DataPin._PIN_TYPES_MAPPING[self.pintype]
        # Get visibility based on el_type
        if el_type == DrawingPin.PinElectricalType.EL_TYPE_NC:
            visibility = DrawingPin.PinVisibility.INVISIBLE
        else:
            visibility = DrawingPin.PinVisibility.VISIBLE
        # Make the DrawingPin
        return DrawingPin(
            Point(0, 0),
            self.num,
            name=self.name,
            el_type=el_type,
            visibility=visibility,
            altfuncs=self.altfuncs,
            **kwargs,
        )


class Device:
    

    _SPECIAL_PIN_MAPPING = {
        "PC14OSC32_IN": ["PC14"],
        "PC15OSC32_OUT": ["PC15"],
        "PF11BOOT0": ["PF11"],
        "OSC_IN": [""],
        "OSC_OUT": [""],
        "VREF-": ["VREF-"],
        "VREFSD-": ["VREFSD-"],
    }
    _SPECIAL_TYPES_MAPPING = {"RCC_OSC_IN": "Clock", "RCC_OSC_OUT": "Clock"}
    _POWER_PAD_FIX_PACKAGES = {"UFQFPN32", "UFQFPN48", "VFQFPN36"}
    _FOOTPRINT_MAPPING = {
        "EWLCSP49-DIE447": "Package_CSP:ST_WLCSP-49_Die447",
        "EWLCSP66-DIE411": "Package_CSP:ST_WLCSP-66_Die411",
        "LFBGA100": "Package_BGA:LFBGA-100_10x10mm_Layout10x10_P0.8mm",
    }
    _FPFILTER_MAPPING = {
        "EWLCSP49-DIE447": "ST_WLCSP*Die447*",
        "EWLCSP66-DIE411": "ST_WLCSP*Die411*",
    }

    pdfinfo = {}

    def __init__(self, name, package, pins):
        self.name = name
        self.package = package
        self.footprint = ""
        self.pins = pins
        self.derived_symbols = []
        self.family = "CH334"


    def create_symbol(self, lib):
        # Make strings for DCM entries
        voltstr = "5V"
        pkgstr = "ASDASD"
        desc_fmt = (
            f'CH344{self.name.replace("CH344", "")}'
            f"{pkgstr}"
        )
        keywords = f"{self.family}"
        datasheet = f"http://www.wch-ic.com/downloads/file/327.html?time=2022-08-26%2005:32:11&code=BCP9Jp3VhB3SFDWU72Zhclbvu2z3Mvg1xfHFhw4f"
        

        # Get footprint filters
        try:
            footprint_filters = Device._FPFILTER_MAPPING[self.package]
        except KeyError:
            footprint_filters = ""
            logging.warning(
                f"No footprint filters found for device"
                f" {self.name}, package {self.package}"
            )

        libname = os.path.basename(lib.filename)
        libname = os.path.splitext(libname)[0]

        # Make the symbol
        self.symbol = kicad_sym.KicadSymbol.new(
            self.name,
            libname,
            "U",
            self.footprint,
            datasheet,
            keywords,
            desc_fmt,
            footprint_filters,
        )

        lib.symbols.append(self.symbol)

        # Draw the symbol
        self.draw_symbol()

        # Add derived symbols
        for i, derived_sym_name in enumerate(self.derived_symbols):
            f = 0 if len(self.flash) == 1 else i + 1
            r = 0 if len(self.ram) == 1 else i + 1

            description = desc_fmt.format(flash=self.flash[f], ram=self.ram[r])

            derived_symbol = kicad_sym.KicadSymbol.new(
                derived_sym_name,
                libname,
                "U",
                self.footprint,
                datasheet,
                keywords,
                description,
                footprint_filters,
            )

            derived_symbol.extends = self.symbol.name

            parent_property = self.symbol.get_property("Reference")
            derived_symbol.get_property("Reference").posx = parent_property.posx
            derived_symbol.get_property("Reference").posy = parent_property.posy
            derived_symbol.get_property(
                "Reference"
            ).effects.h_justify = parent_property.effects.h_justify

            parent_property = self.symbol.get_property("Value")
            derived_symbol.get_property("Value").posx = parent_property.posx
            derived_symbol.get_property("Value").posy = parent_property.posy
            derived_symbol.get_property(
                "Value"
            ).effects.h_justify = parent_property.effects.h_justify

            parent_property = self.symbol.get_property("Footprint")
            derived_symbol.get_property("Footprint").posx = parent_property.posx
            derived_symbol.get_property("Footprint").posy = parent_property.posy
            derived_symbol.get_property(
                "Footprint"
            ).effects.h_justify = parent_property.effects.h_justify
            derived_symbol.get_property(
                "Footprint"
            ).effects.is_hidden = parent_property.effects.is_hidden

            lib.symbols.append(derived_symbol)

    def draw_symbol(self):
        resetPins = []
        bootPins = []
        powerPins = []
        clockPins = []
        ncPins = []
        otherPins = []
        upstreamPins = []
        downstreamPins = []
        overcurrentPins = []
        ports = {}

        topPins = []
        bottomPins = []

        # Get pin length
        pin_length = 200

        # Classify pins
        for pin in self.pins:

            # TODO: Add logic for upstramm/downstream
            # I/O pins - uncertain orientation
            if (pin.pintype == "I/O" or pin.pintype == "Clock") and pin.name.startswith(
                "P"
            ):
                port = pin.name[1]
                pin_num = int(Device._number_findall.findall(pin.name)[0])
                try:
                    ports[port][pin_num] = pin.to_drawing_pin(pin_length=pin_length)
                except KeyError:
                    ports[port] = {}
                    ports[port][pin_num] = pin.to_drawing_pin(pin_length=pin_length)
            # Clock pins go on the left
            elif pin.pintype == "Clock":
                clockPins.append(
                    pin.to_drawing_pin(
                        pin_length=pin_length,
                        orientation=DrawingPin.PinOrientation.RIGHT,
                    )
                )
            # Power pins
            elif pin.pintype == "Power" or pin.name.startswith("VREF"):
                # Positive pins go on the top
                if pin.name.startswith("VDD") or pin.name.startswith("VBAT") or pin.name.startswith("5V"):
                    topPins.append(
                        pin.to_drawing_pin(
                            pin_length=pin_length,
                            orientation=DrawingPin.PinOrientation.DOWN,
                        )
                    )
                # Negative pins go on the bottom
                elif pin.name.startswith("VSS") or pin.name.startswith("GND"):
                    bottomPins.append(
                        pin.to_drawing_pin(
                            pin_length=pin_length,
                            orientation=DrawingPin.PinOrientation.UP,
                        )
                    )
                # Other pins go on the left
                else:
                    powerPins.append(
                        pin.to_drawing_pin(
                            pin_length=pin_length,
                            orientation=DrawingPin.PinOrientation.RIGHT,
                        )
                    )
            # Reset pins go on the left
            elif pin.pintype == "Reset":
                resetPins.append(
                    pin.to_drawing_pin(
                        pin_length=pin_length,
                        orientation=DrawingPin.PinOrientation.RIGHT,
                    )
                )
            # Boot pins go on the left
            elif pin.pintype == "Boot":
                bootPins.append(
                    pin.to_drawing_pin(
                        pin_length=pin_length,
                        orientation=DrawingPin.PinOrientation.RIGHT,
                    )
                )
            # NC pins go in their own group
            elif pin.pintype == "NC":
                ncPins.append(
                    pin.to_drawing_pin(
                        pin_length=pin_length,
                        orientation=DrawingPin.PinOrientation.RIGHT,
                    )
                )
            elif pin.pintype == "Upstream":
                upstreamPins.append(
                    pin.to_drawing_pin(
                        pin_length=pin_length,
                        orientation=DrawingPin.PinOrientation.RIGHT,
                    )
                )
            elif pin.pintype == "Downstream":
                downstreamPins.append(
                    pin.to_drawing_pin(
                        pin_length=pin_length,
                        orientation=DrawingPin.PinOrientation.LEFT,
                    )
                )
            elif pin.pintype == "Overcurrent":
                overcurrentPins.append(
                    pin.to_drawing_pin(
                        pin_length=pin_length,
                        orientation=DrawingPin.PinOrientation.LEFT,
                    )
                )
            # Other pins go on the left
            else:
                otherPins.append(
                    pin.to_drawing_pin(
                        pin_length=pin_length,
                        orientation=DrawingPin.PinOrientation.RIGHT,
                    )
                )

        # Apply pins to sides
        leftGroups = []
        rightGroups = []

        leftSpace = 0
        rightSpace = 0

        # Special groups go to the left
        if resetPins:
            leftGroups.append(resetPins)
        if bootPins:
            leftGroups.append(bootPins)
        if powerPins:
            leftGroups.append(sorted(powerPins, key=lambda p: p.name))
        if clockPins:
            leftGroups.append(clockPins)
        if otherPins:
            leftGroups.append(otherPins)
        if upstreamPins:
            leftGroups.append(upstreamPins)
        if downstreamPins:
            rightGroups.append(downstreamPins)
        if overcurrentPins:
            rightGroups.append(overcurrentPins)

        logging.debug(len(upstreamPins))
        # Count the space needed for special groups
        for group in leftGroups:
            leftSpace += len(group) + 1

        # Add ports to the right, counting the space needed
        for _, port in sorted(ports.items()):
            pins = [pin for _, pin in sorted(port.items())]
            rightSpace += len(pins) + 1
            rightGroups.append(pins)

        # Calculate height of the symbol
        leftPins = 0
        rightPins = 0
        for group in leftGroups:
            leftPins += 100
            for p in group:
                leftPins += 100
        for group in rightGroups:
            rightPins += 100
            for p in group:
                rightPins += 100

        for pin in ncPins:
            leftPins += 100

        box_height = max(leftPins, rightPins) + 100

        # Calculate the width of the symbol
        def round_up(x, y):
            return (x + y - 1) // y * y

        def pin_group_max_width(group):
            return max(len(p.name) * 47 for p in group)

        left_width = round_up(
            max(pin_group_max_width(group) for group in leftGroups), 100
        )
        right_width = round_up(
            max(pin_group_max_width(group) for group in rightGroups), 100
        )
        top_width = len(topPins) * 100
        bottom_width = len(bottomPins) * 100
        middle_width = 100 + max(top_width, bottom_width)
        box_width = left_width + middle_width + right_width

        drawing = Drawing()

        # Add the body rectangle
        drawing.append(
            DrawingRectangle(
                Point(0, 0),
                Point(box_width, box_height),
                unit_idx=0,
                fill=ElementFill.FILL_BACKGROUND,
            )
        )

        # Add the moved pins (bottom left)
        y = 100

        # Add the left pins (top left)
        y = box_height - 100
        for group in leftGroups:
            for pin in group:
                pin.at = Point(-pin_length, y)
                pin.orientation = DrawingPin.PinOrientation.RIGHT
                drawing.append(pin)
                y -= 100
            y -= 100

        # Add the right pins
        y = 100
        for group in reversed(rightGroups):
            for pin in reversed(group):
                pin.at = Point(box_width + pin_length, y)
                pin.orientation = DrawingPin.PinOrientation.LEFT
                drawing.append(pin)
                y += 100
            y += 100

        # Add the top pins
        x = (left_width + (100 + middle_width) // 2 - top_width // 2) // 100 * 100
        for pin in sorted(topPins, key=lambda p: p.name):
            pin.at = Point(x, box_height + pin_length)
            pin.orientation = DrawingPin.PinOrientation.DOWN
            drawing.append(pin)
            x += 100
        last_top_x = x

        # Add the bottom pins
        x = (left_width + (100 + middle_width) // 2 - bottom_width // 2) // 100 * 100
        for pin in sorted(bottomPins, key=lambda p: p.name):
            pin.at = Point(x, -pin_length)
            pin.orientation = DrawingPin.PinOrientation.UP
            drawing.append(pin)
            x += 100

        # Add the NC pins
        y = 100
        for pin in ncPins:
            pin.at = Point(0, y)
            pin.orientation = DrawingPin.PinOrientation.RIGHT
            drawing.append(pin)
            y += 100
        y += 100

        # Center the symbol
        translate_center = Point(
            -box_width // 2 // 100 * 100, -box_height // 2 // 100 * 100
        )
        drawing.translate(translate_center)

        property = self.symbol.get_property("Reference")
        pos = Point(0, box_height + 50).translate(translate_center)
        property.set_pos_mil(pos.x, pos.y, 0)
        property.effects.h_justify = "left"

        property = self.symbol.get_property("Value")
        pos = Point(last_top_x, box_height + 50).translate(translate_center)
        property.set_pos_mil(pos.x, pos.y, 0)
        property.effects.h_justify = "left"

        property = self.symbol.get_property("Footprint")
        pos = translate_center
        property.set_pos_mil(pos.x, pos.y, 0)
        property.effects.h_justify = "right"
        property.effects.is_hidden = True

        drawing.appendToSymbol(self.symbol)

def main():
    logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.DEBUG)
    libraries = {}

    with open("/Users/carlo/Documents/iphone_fi/kicad-library-utils/symbol-generators/CH334/CH334DS1.csv", "r") as f:
        pinreader = csv.reader(f)
        pins = list(pinreader)

    package_pins = {}
    chip_versions = pins[0][0].split(';')[:-2]
    for chip_version in chip_versions:
        package_pins[chip_version] = []

    for pin in pins[1:]:
        something = pin[0].split(";")
        for pin_number, key in zip(something[:-2], chip_versions):
            if len(pin_number.split('.')) != 1:
                for pins in pin_number.split('.'):
                    package_pins[key].append(DataPin(pins, something[7], something[8]))
            else:
                if pin_number != "-":
                    package_pins[key].append(DataPin(pin_number, something[7], something[8]))


    hubs = []

    pakages = {
        "335F": "QFN28_4x4",
        "334G": "SOP16",
        "334R": "QSOP16",
        "334F":	"QFN24_4x4",
        "334U": "QSOP28",
        "334S": "SSOP28",
        "334H": "QFN28_5x5",
        "334L": "LQFP48"
    }

    for device_ in package_pins.items():
        if device_[0] == "G/R":
            hubs.append(Device("334G", "334G", device_[1]))
            hubs.append(Device("334R", "334R", device_[1]))
            continue
        hubs.append(Device(device_[0], pakages[device_[0]], device_[1]))
    
    for hub in hubs:
        # If there isn't a SymbolGenerator for this family yet, make one
        if hub.family not in libraries:
            libraries[hub.family] = kicad_sym.KicadLibrary(
                f'{hub.family}_{datetime.now().strftime("%H_%M_%S")}.kicad_sym'
            )
        # If the part has a datasheet PDF, make a symbol for it
        hub.create_symbol(libraries[hub.family])

    # Write libraries
    for gen in libraries.values():
        gen.write()

if __name__ == "__main__":
    main()
