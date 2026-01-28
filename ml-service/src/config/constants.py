"""
Centralized constants for ML service.
Single source of truth for model names, detection thresholds, and color ranges.
"""

# Model Configuration
MODELS = {
    "yolo": "yolov8n.pt",
    "clip": "openai/clip-vit-base-patch32",
}

# Detection Thresholds
DAMAGE_DETECTION = {
    "min_confidence": 0.3,
    "max_frames": 15,
    "min_area": 500,
    "max_area": 100000,
    "circularity_threshold": 0.4,
    "scratch_min_area": 500,
    "scratch_max_area": 20000,
    "dent_min_area": 2000,
    "dent_max_area": 100000,
    "rust_min_area": 500,
    "rust_max_area": 50000,
}

# Vehicle type mappings from YOLO class indices
VEHICLE_TYPES = {
    2: "car",       # car
    3: "motorcycle", # motorcycle
    5: "bus",       # bus
    7: "truck",     # truck
}

# Color Detection Ranges (HSV format)
# Each color has lower and upper bounds for HSV values
# Red has two ranges because it wraps around the hue spectrum
COLOR_RANGES = {
    "white": {
        "lower": (0, 0, 200),
        "upper": (180, 30, 255),
    },
    "black": {
        "lower": (0, 0, 0),
        "upper": (180, 255, 50),
    },
    "gray": {
        "lower": (0, 0, 50),
        "upper": (180, 30, 200),
    },
    "silver": {
        "lower": (0, 0, 150),
        "upper": (180, 20, 220),
    },
    "red": {
        # Red wraps around hue 0/180, so we need two ranges
        "lower": [(0, 100, 100), (160, 100, 100)],
        "upper": [(10, 255, 255), (180, 255, 255)],
    },
    "blue": {
        "lower": (100, 100, 100),
        "upper": (130, 255, 255),
    },
    "green": {
        "lower": (35, 100, 100),
        "upper": (85, 255, 255),
    },
    "yellow": {
        "lower": (20, 100, 100),
        "upper": (35, 255, 255),
    },
    "orange": {
        "lower": (10, 100, 100),
        "upper": (20, 255, 255),
    },
    "brown": {
        "lower": (10, 100, 50),
        "upper": (20, 255, 150),
    },
    "beige": {
        "lower": (15, 30, 150),
        "upper": (25, 80, 220),
    },
    "gold": {
        "lower": (20, 100, 150),
        "upper": (30, 255, 255),
    },
    "purple": {
        "lower": (130, 100, 100),
        "upper": (160, 255, 255),
    },
    "pink": {
        "lower": (150, 50, 150),
        "upper": (170, 150, 255),
    },
}

# Priority order for color detection (most common vehicle colors first)
COLOR_PRIORITY = [
    "white",
    "black",
    "silver",
    "gray",
    "red",
    "blue",
    "green",
    "brown",
    "beige",
    "gold",
    "yellow",
    "orange",
    "purple",
    "pink",
]
