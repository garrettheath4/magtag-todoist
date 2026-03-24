# MagTag Todoist

Display high-priority Todoist tasks on an Adafruit MagTag.


## Quickstart

1.  Follow [this guide](https://circuitpython.org/board/adafruit_magtag_2.9_grayscale/) to update your MagTag's
    bootloader and CircuitPython firmware to the latest versions.
1.  Clone this repository and its Git submodules:

    ```shell
    git clone https://github.com/garrettheath4/magtag-todoist.git
    cd magtag-todoist/
    ```

1.  Download the latest CircuitPython libraries [from here](https://circuitpython.org/libraries):
    *   Bundle for Version 10.x (or whatever the latest version is)
    *   Python Source Bundle
1.  Decompress the downloaded files. They should each contain one folder. Move these folders into the `lib` folder in
    this repo (which you might first have to create with `mkdir lib`).
1.  Update the `PROD_LIB` and `DEV_LIB` variables in `Makefile` with the paths to the latest-version bundle and source
    bundle, respectively.
1.  Plug in MagTag to your computer with a USB-C cable and turn the physical switch on it to the _On_ position. A
    flash-drive-like file storage device called _CIRCUITPY_ should automatically mount.
1.  Run `make` to copy the code and required libraries from this repository to the _CIRCUITPY_ drive.
1.  Create a `my_secrets.py` file inside the _CIRCUITPY_ drive with the following contents:

    ```python
    # This file is where you keep secret settings, passwords, and tokens!
    # If you put them in the code you risk committing that info or sharing it

    my_secrets = {
        'ssid': 'myWifiNetworkName',
        'password': 'myWifiPassword',
        'todoist_api_key': '1234567890abcdefghijklmnopqrstuvwxyz',
        'timezone': "America/New_York"  # https://time.now/developer
    }
    ```

1.  Wait for the MagTag to restart and the code will run automatically.


## Debugging

If you see `ImportError: no module named 'warnings'`, your CircuitPython build is older than what current
`adafruit_portalbase` expects. Either **upgrade** CircuitPython to a recent 9.x build for MagTag, or run `make` so
`circuitpython_stubs/warnings.py` is copied to `CIRCUITPY/lib/warnings.py` (no-op shim).

If you see `AttributeError: 'EPaperDisplay' object has no attribute 'root_group'`, your **firmware is older** than the
display API expected by current `adafruit_portalbase` / `adafruit_magtag.graphics`. This project’s `code.py` avoids the
high-level `MagTag()` helper and uses `displayio` + `display.show()` when `root_group` is missing, so it should run on
those boards; upgrading CircuitPython to match your library bundle (e.g. 9.x) is still recommended.

If you see `AttributeError: 'module' object has no attribute 'getenv'` from `adafruit_portalbase/network.py`, your
CircuitPython `os` module is too old for current PortalBase. This project connects with **`wifi.radio` +
`adafruit_requests`** instead, so that path should not appear once `code.py` is updated.

`Glyph not found` on startup usually means a **Unicode character** (e.g. `…`) is not in `terminalio.FONT`; this project
uses ASCII `...` for placeholders.

If you see `TypeError: unsupported type for __hash__: 'SocketPool'` inside `adafruit_connection_manager`, use
**`adafruit_connection_manager.get_radio_socketpool(wifi.radio)`** (not `socketpool.SocketPool(wifi.radio)`) when creating
`adafruit_requests.Session` — current `adafruit_requests` expects the connection-manager pool wrapper. Ensure
`adafruit_connection_manager.mpy` is on `CIRCUITPY/lib/` (included in this repo’s `make prod` list).

`No network with that ssid` means the MagTag can’t see your AP: use the **2.4 GHz** network (ESP32-S2 does not do 5 GHz),
check the SSID/password in `my_secrets.py`, and fix typos / hidden spaces (the code strips leading/trailing whitespace).

Run the following command to connect to the MagTag debug console using `screen` in a terminal:

```shell
screen /dev/tty.usbmodemC7FD1A7142021 115200
```


## Requirements

* [Adafruit MagTag 2.9" E-Ink WiFi Display](https://www.adafruit.com/product/4800)
* Todoist API key



<!-- vim: set textwidth=120 columns=125 smarttab shiftround expandtab nosmartindent: -->
