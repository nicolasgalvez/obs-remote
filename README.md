# OBS VCR Remote

OBS Studio Python script that sends VCR control commands (POWER, PLAY, STOP,
REW, FF, EJECT, PAUSE) over USB serial to an ESP32 running the Panasonic
PV-V4525S IR remote firmware (sibling PlatformIO project
`ESP32 VCR Remote`).

Works on macOS, Linux, and Windows.

## Install

### 1. Install pyserial into OBS's Python

OBS uses its own Python interpreter, set under **Tools → Scripts → Python
Settings**. Install `pyserial` into that interpreter.

**macOS** (OBS typically uses the system Python 3):

```sh
/usr/local/bin/python3 -m pip install --user pyserial
# or whatever path is shown in OBS's Python Settings
```

**Linux**:

```sh
python3 -m pip install --user pyserial
```

**Windows** (from a cmd/PowerShell window):

```powershell
# Use the Python you pointed OBS at. Typical install:
"C:\Program Files\Python311\python.exe" -m pip install pyserial
```

Tip: the exact interpreter path OBS is using is shown in **Tools → Scripts
→ Python Settings**. Install `pyserial` against that same path.

### 2. Load the script

1. OBS → **Tools → Scripts** → **+** → pick `vcr_remote.py`.
2. Pick your ESP32's serial port from the **Serial port** dropdown.
   The label includes the device description (e.g.
   `/dev/cu.usbserial-0001 — CP2102 USB to UART Bridge Controller`) so
   the ESP32 is easy to spot. Hit **Refresh ports** if you plug it in
   after loading the script.
3. Click a **Send <COMMAND>** button under *Test commands* to verify.

### 3. Optional: bind hotkeys

**Settings → Hotkeys** → search for `VCR Remote:` — each command has an
entry you can bind to a key combo.

### 4. Optional: drive commands from scene changes

Under *Scene → Command* in the script properties, type a scene name next
to a command. Switching OBS to that scene will send the command.

### 5. Optional: drive commands from OBS events

Under *OBS Event → Command sequence* you can map OBS frontend events
(recording started/stopped/paused/unpaused, streaming started/stopped,
etc.) to one or more VCR commands. Type a comma-separated sequence:

| Event               | Sequence  | Effect                          |
| ------------------- | --------- | ------------------------------- |
| `RECORDING_STARTED` | `PLAY`    | Roll the tape when REC starts.  |
| `RECORDING_PAUSED`  | `PAUSE`   | VCR follows OBS pause.          |
| `RECORDING_STOPPED` | `STOP,REW`| End-of-tape: stop, then rewind. |

The *Inter-command delay (ms)* setting controls the gap between
sequenced commands (default 400ms — the IR transmitter and the VCR
need a moment between bursts).

This pairs cleanly with
[vhs-automization-script](https://github.com/nicolasgalvez/vhs-automization-script):
that script controls OBS's recording state via WebSocket; the VCR
follows automatically through these event mappings, no extra glue.

## Serial protocol (for reference)

- 115200 baud, 8N1
- Newline-terminated ASCII
- Commands: `POWER`, `PLAY`, `STOP`, `REW`, `FF`, `EJECT`, `PAUSE`
- `?` or `HELP` lists commands (the firmware echoes, the script ignores
  the echo)

## Troubleshooting

- **"pyserial not installed"** in the OBS script log — install pyserial
  into the Python interpreter OBS is using (step 1).
- **Port opens then writes silently fail** — another program may own the
  port (Arduino IDE serial monitor, screen, minicom). Close it.
- **Port isn't in the dropdown** — click **Refresh ports**. On Linux your
  user needs to be in the `dialout` group: `sudo usermod -aG dialout $USER`
  then log out/in. The port field is also editable — you can type a path
  by hand.
