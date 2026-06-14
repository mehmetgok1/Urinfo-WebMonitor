# Urinfo desktopmonitor — Setup Guide

This guide details the environment configuration and dependency installation for the `Urinfo-desktopMonitor` application. 

The application utilizes **PyQt5** for its graphical interface, **OpenCV** for specialized image tracking or frame operations, and **Bleak** for cross-platform Bluetooth Low Energy (BLE) peripheral communications.

---

## Technical Stack & OS Architecture Compatibility

The project relies on specific hardware abstractions that dictate how environments must be deployed:

* **Asynchronous BLE Backend:** Powered by `Bleak` which interfaces natively with the system's Bluetooth daemon (`BlueZ` via `dbus-fast` on Linux, `CoreBluetooth` on macOS, and the Windows Runtime Bluetooth APIs on Windows).
* **Headless Video Core:** Uses `opencv-python-headless` to eliminate package-level X11/Qt binding conflicts with your primary `PyQt5` library while preserving core matrix and frame processing utilities.
* **Target Environments:** Native OS installations (Ubuntu/Debian, Windows 10/11, macOS) are supported. **Docker deployment is not supported** due to hardware-layer constraints regarding containerized D-Bus IPC access and Bluetooth transceiver forwarding.

---

## Installation & Setup Pipeline

Follow these structural steps to configure your localized development workspace without altering system-managed Python environments.

### Step 1: Initialize the Isolated Virtual Environment

Navigate to the project root directory where your application files reside, and build a local isolated `.venv` sandbox:

```bash
# Navigate to your application scope
cd /home/deso/delete/Urinfo-WebMonitor/python_app/

# Ensure core virtual environment binaries are present on your host system
sudo apt update && sudo apt install python3-venv

# Create a clean virtual environment mapping
python3 -m venv .venv

# Activate the virtual environment
source .venv/bin/activate

# install dependencies
pip install -r requirements.txt

# run the program
python3 main.py