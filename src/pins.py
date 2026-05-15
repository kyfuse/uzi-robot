"""
Physical pin to Blinka pin mapping on a Jetson Orin Nano.
"""

import warnings

# Jetson.GPIO warns when /dev/mem is unreadable; pinmux checks are optional for Blinka.
warnings.filterwarnings(
    "ignore",
    category=UserWarning,
    module=r"Jetson\.GPIO\.gpio_cdev",
    message=r"Could not open /dev/mem for pinmux check\.",
)

import board  # noqa: E402

LED = board.D19  # Physical pin 35 (I2SO_FS)

TFT_CS = board.D8  # Physical pin 24 (SPI0_CS0)
TFT_DC = board.D24  # Physical pin 18 (SPI1_CSI0)
TFT_RESET = board.D23  # Physical pin 16 (SPI1_CSI1)
