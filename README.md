# Uzi

Uzi from Murder Drones, but in real life (with less murdering).

## Jetson Setup

Setup the Jetson Orin Nano Developer Kit by following [this](https://developer.nvidia.com/embedded/learn/get-started-jetson-orin-nano-devkit#firmware).

- Firmware should be >= 36.5.0 with JetPack 6.2.1. It will be running Ubuntu 22.
- The SD card slot is in the middle of the fan and the bottom of the board. It should snap into place.

Upgrade to JetPack 6.2.2 by following [this](https://forums.developer.nvidia.com/t/jetpack-6-2-2-jetson-linux-36-5-is-now-live/359622).

```sh
echo "Setting up Jetson..."
sudo apt-get update
sudo apt-get upgrade

# Downgrade to an older Snap version to allow apps to install (see https://forums.developer.nvidia.com/t/chromium-other-browsers-not-working-after-flashing-or-updating-heres-why-and-quick-fix/338891)
snap download snapd --revision=24724
sudo snap ack snapd_24724.assert
sudo snap install snapd_24724.snap
sudo sudo snap refresh --hold snapd

# Install Chromium
sudo apt-get install -y chromium-browser

# Packages and tools
sudo apt-get install -y fzf htop software-properties-common portaudio19-dev minicom fonts-dejavu
echo 'source /usr/share/doc/fzf/examples/key-bindings.bash' >> ~/.bashrc  # Ctrl-R history fuzzy search

# Remote VNC server (remote desktop)
sudo apt-get install -y tigervnc-standalone-server
gsettings set org.gnome.desktop.screensaver lock-enabled false  # Fixes remote perma-lock bug
# Run over SSH: vncserver :1 -geometry 1920x1080 -depth 24 -localhost no
# Stop it later: vncserver -kill :1
# Connect: vnc://192.168.55.1:5901 (or the IP shown with ifconfig)

# Set microphone input source to ReSpeaker mic
pactl set-default-source alsa_input.usb-SEEED_ReSpeaker_4_Mic_Array__UAC1.0_-00.multichannel-input

# Install helper tools
sudo snap install zellij --classic  # Zellij
curl -LsSf https://astral.sh/uv/install.sh | sh  # uv

# Install Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
# Also install Tailscale on your local machine
# Then you can SSH / setup remote VS Code using Tailscale's assigned IP/domain name

# Setup systemd service
sudo cp uzi-robot.service /etc/systemd/system/uzi-robot.service
sudo systemctl daemon-reload  # Reloads the config .service file
# sudo systemctl [enable/disable] --now uzi-robot.service: Changes the service to run/stop now/on startup.

echo "Setup complete!"
```

## Python Setup

```sh
# Make uv project and venv
uv init
uv venv
uv pip install -r requirements.txt

uv pip install setuptools spidev pyaudio

sudo $(which python) tuning.py
```

## Temp

```sh
sudo usermod -aG i2c,gpio,dialout uzi
uv add adafruit-blinka adafruit-circuitpython-pca9685 adafruit-circuitpython-servokit adafruit-circuitpython-bno08x
```

These pins need to be explicitly configured, ex: as GPIO, for them to work:

```sh
sudo /opt/nvidia/jetson-io/jetson-io.py
# Set pin 35 to GPIO, enable I2C, SPI1, and UART
```
