"""
Physical pin to Blinka pin mapping on a Jetson Orin Nano.
"""

import board

"""
Board pin -> SoC pin name -> Jetson physical pin #, Jetson pin name
D10 -> GP49_SPI1_MOSI
D11 -> GP47_SPI1_CLK
D12 -> GP113_PWM7
D13 -> GP115
D16 -> GP73_UART1_CTS_N
D17 -> GP72_UART1_RTS_N
D18 -> GP122
D19 -> GP125 -> 35, I2SO_FS
D20 -> GP124
D21 -> GP123
D22 -> GP88_PWM1
D23 -> GP40_SPI3_CS1_N -> 16, SPI1_CSI1
D24 -> GP39_SPI3_CS0_N -> 18, SPI1_CSI0
D25 -> GP37_SPI3_MISO
D26 -> GP38_SPI3_MOSI
D27 -> SPI1_SCK
D4 -> GP167
D5 -> GP65 -> 29, GPIO01
D6 -> GP66
D7 -> GP51_SPI1_CS1_N
D8 -> GP50_SPI1_CS0_N -> 24, SPI0_CS0
D9 -> GP48_SPI1_MISO
"""
# for pin in [x for x in dir(board) if x.startswith("D")]:
#     print(f"{pin} -> {getattr(board, pin)}")

STATUS_LED = board.D19  # Physical pin 35 (I2SO_FS)

TFT_CS = board.D8  # Physical pin 24 (SPI0_CS0)
TFT_DC = board.D24  # Physical pin 18 (SPI1_CSI0)
TFT_RESET = board.D23  # Physical pin 16 (SPI1_CSI1)

# # BNO085 IMU (UART-RVC mode on UART1)
# # TX/RX are claimed by the kernel UART driver — use pyserial,
# # not Blinka, to talk to /dev/ttyTHS0
# IMU_UART = "/dev/ttyTHS0"
# IMU_BAUD = 115200

# # PCA9685 servo driver (I2C bus 7, pins 3 & 5)
# SERVO_I2C_BUS = 7
# SERVO_I2C_ADDR = 0x40

# # TFT (ILI9341) on SPI0
# TFT_SPI_BUS = 0
# TFT_SPI_DEV = 0  # /dev/spidev0.0 (CS0, physical pin 24)
# TFT_DC = board.D17  # physical pin 11
# TFT_RESET = board.D27  # physical pin 13
# TFT_BACKLIGHT = board.D22  # physical pin 15
