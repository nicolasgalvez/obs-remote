"""OBS Studio Python script: VCR Remote.

Sends control commands over USB serial to an ESP32 running the
Panasonic PV-V4525S VCR IR remote firmware (sibling project under
~/Documents/PlatformIO/Projects/ESP32 VCR Remote).

The firmware accepts newline-terminated ASCII at 115200 baud:
  POWER, PLAY, STOP, REW, FF, EJECT, PAUSE

Install (Tools > Scripts > +):
  - Add this file.
  - Set Python path under Tools > Scripts > Python Settings if needed.
  - Requires `pyserial` in OBS's Python environment.
"""

import glob
import platform

import obspython as obs

try:
    import serial  # pyserial
    from serial.tools import list_ports as _list_ports
except ImportError:
    serial = None
    _list_ports = None


COMMANDS = ["POWER", "PLAY", "STOP", "REW", "FF", "EJECT", "PAUSE"]
BAUD = 115200
DEFAULT_INTER_COMMAND_MS = 400

# OBS frontend events the user can map to VCR command sequences.
# Resolved lazily because older OBS builds may not expose every constant.
_EVENT_NAMES = [
    "RECORDING_STARTING",
    "RECORDING_STARTED",
    "RECORDING_STOPPING",
    "RECORDING_STOPPED",
    "RECORDING_PAUSED",
    "RECORDING_UNPAUSED",
    "STREAMING_STARTING",
    "STREAMING_STARTED",
    "STREAMING_STOPPING",
    "STREAMING_STOPPED",
]


def _supported_events():
    """Return [(name, code)] for events this OBS build actually defines."""
    out = []
    for name in _EVENT_NAMES:
        code = getattr(obs, f"OBS_FRONTEND_EVENT_{name}", None)
        if code is not None:
            out.append((name, code))
    return out


# Module-level state. OBS scripts are reloaded on edit, so we keep this flat.
_state = {
    "port_path": "",
    "serial": None,
    "hotkey_ids": {},       # command -> obs_hotkey_id
    "scene_commands": {},   # scene name (str) -> command (str)
    "last_scene": None,
    "event_commands": {},   # event name (str) -> [command, command, ...]
    "event_code_to_name": {},
    "inter_command_ms": DEFAULT_INTER_COMMAND_MS,
}


# ---------------------------------------------------------------------------
# Serial port helpers
# ---------------------------------------------------------------------------

def list_serial_ports():
    """Enumerate USB-serial devices. Returns list of (device, label) tuples.

    Prefers pyserial's list_ports (works on macOS, Linux, Windows and
    provides human-readable descriptions). Falls back to /dev globs when
    pyserial isn't installed yet — that path won't hit on Windows, but
    the user can always type the COM port into the editable combo.
    """
    results = []
    if _list_ports is not None:
        for info in _list_ports.comports():
            desc = info.description or ""
            # Skip entries that are clearly not a USB-serial device on Linux
            # (e.g. /dev/ttyS0 built-in UARTs with "n/a" descriptions).
            if desc in ("", "n/a") and info.device.startswith("/dev/ttyS"):
                continue
            label = f"{info.device} — {desc}" if desc and desc != "n/a" else info.device
            results.append((info.device, label))
    else:
        system = platform.system()
        if system == "Darwin":
            patterns = [
                "/dev/cu.usbserial*", "/dev/cu.usbmodem*",
                "/dev/cu.wchusbserial*", "/dev/cu.SLAB_USBtoUART*",
            ]
        elif system == "Linux":
            patterns = ["/dev/ttyUSB*", "/dev/ttyACM*"]
        else:
            patterns = []
        seen = set()
        for pat in patterns:
            for dev in glob.glob(pat):
                if dev not in seen:
                    seen.add(dev)
                    results.append((dev, dev))
    results.sort(key=lambda r: r[0])
    return results


def open_serial(port_path):
    close_serial()
    if not port_path:
        return
    if serial is None:
        obs.script_log(obs.LOG_WARNING,
                       "VCR Remote: pyserial not installed. See README.")
        return
    try:
        _state["serial"] = serial.Serial(port_path, BAUD, timeout=0.5)
        obs.script_log(obs.LOG_INFO, f"VCR Remote: opened {port_path}")
    except Exception as e:
        obs.script_log(obs.LOG_WARNING,
                       f"VCR Remote: failed to open {port_path}: {e}")
        _state["serial"] = None


def close_serial():
    s = _state.get("serial")
    if s is not None:
        try:
            s.close()
        except Exception:
            pass
    _state["serial"] = None


def send_command(cmd):
    """Write `CMD\\n` to the serial port, reopening if needed."""
    if cmd not in COMMANDS:
        obs.script_log(obs.LOG_WARNING, f"VCR Remote: unknown command {cmd!r}")
        return
    s = _state.get("serial")
    if s is None or not getattr(s, "is_open", False):
        open_serial(_state.get("port_path", ""))
        s = _state.get("serial")
    if s is None:
        return
    try:
        s.write((cmd + "\n").encode("ascii"))
        s.flush()
        obs.script_log(obs.LOG_INFO, f"VCR Remote: sent {cmd}")
    except Exception as e:
        obs.script_log(obs.LOG_WARNING, f"VCR Remote: write failed: {e}")
        close_serial()


# ---------------------------------------------------------------------------
# Command sequencing
# ---------------------------------------------------------------------------

def parse_sequence(text):
    """Parse 'STOP, REW' / 'STOP;REW' / 'stop rew' into ['STOP', 'REW']."""
    if not text:
        return []
    out = []
    for tok in text.replace(";", ",").replace(" ", ",").split(","):
        tok = tok.strip().upper()
        if not tok:
            continue
        if tok in COMMANDS:
            out.append(tok)
        else:
            obs.script_log(obs.LOG_WARNING,
                           f"VCR Remote: ignoring unknown command {tok!r}")
    return out


def run_sequence(seq):
    """Send a list of commands with the configured inter-command delay.

    First command goes immediately; the rest are scheduled via OBS's
    timer so we don't block the UI thread.
    """
    if not seq:
        return
    delay_ms = max(50, int(_state.get("inter_command_ms",
                                      DEFAULT_INTER_COMMAND_MS)))
    seq = list(seq)
    send_command(seq[0])
    if len(seq) == 1:
        return
    idx = [1]

    def step():
        obs.remove_current_callback()  # one-shot
        if idx[0] >= len(seq):
            return
        send_command(seq[idx[0]])
        idx[0] += 1
        if idx[0] < len(seq):
            obs.timer_add(step, delay_ms)

    obs.timer_add(step, delay_ms)


# ---------------------------------------------------------------------------
# OBS frontend events
# ---------------------------------------------------------------------------

def on_frontend_event(event):
    if event == obs.OBS_FRONTEND_EVENT_SCENE_CHANGED:
        src = obs.obs_frontend_get_current_scene()
        if src is None:
            return
        try:
            name = obs.obs_source_get_name(src)
        finally:
            obs.obs_source_release(src)
        handle_scene_change(name)
        return

    name = _state["event_code_to_name"].get(event)
    if name is None:
        return
    seq = _state["event_commands"].get(name)
    if seq:
        obs.script_log(obs.LOG_INFO,
                       f"VCR Remote: event {name} → {','.join(seq)}")
        run_sequence(seq)


def handle_scene_change(scene_name):
    if scene_name == _state.get("last_scene"):
        return
    _state["last_scene"] = scene_name
    cmd = _state["scene_commands"].get(scene_name)
    if cmd:
        send_command(cmd)


# ---------------------------------------------------------------------------
# Hotkey callbacks
# ---------------------------------------------------------------------------

def _make_hotkey_cb(cmd):
    def cb(pressed):
        if pressed:
            send_command(cmd)
    return cb


def _make_test_button_cb(cmd):
    def cb(props, prop):
        send_command(cmd)
        return False  # no property refresh
    return cb


def _refresh_ports_cb(props, prop):
    port_prop = obs.obs_properties_get(props, "port_path")
    obs.obs_property_list_clear(port_prop)
    obs.obs_property_list_add_string(port_prop, "(none)", "")
    for device, label in list_serial_ports():
        obs.obs_property_list_add_string(port_prop, label, device)
    return True  # refresh UI


# ---------------------------------------------------------------------------
# OBS script lifecycle
# ---------------------------------------------------------------------------

def script_description():
    return (
        "<b>VCR Remote</b><br/>"
        "Sends VCR control commands over USB serial to an ESP32 running the "
        "Panasonic PV-V4525S IR remote firmware.<br/><br/>"
        "Requires <code>pyserial</code> in OBS's Python. See README."
    )


def script_defaults(settings):
    obs.obs_data_set_default_string(settings, "port_path", "")
    obs.obs_data_set_default_int(settings, "inter_command_ms",
                                 DEFAULT_INTER_COMMAND_MS)
    for c in COMMANDS:
        obs.obs_data_set_default_string(settings, f"scene_{c}", "")
    for name, _ in _supported_events():
        obs.obs_data_set_default_string(settings, f"event_{name}", "")


def script_properties():
    props = obs.obs_properties_create()

    port_prop = obs.obs_properties_add_list(
        props, "port_path", "Serial port",
        obs.OBS_COMBO_TYPE_EDITABLE, obs.OBS_COMBO_FORMAT_STRING,
    )
    obs.obs_property_list_add_string(port_prop, "(none)", "")
    for device, label in list_serial_ports():
        obs.obs_property_list_add_string(port_prop, label, device)

    obs.obs_properties_add_button(
        props, "refresh_ports", "Refresh ports", _refresh_ports_cb,
    )

    # Manual test buttons
    test_grp = obs.obs_properties_create()
    for c in COMMANDS:
        obs.obs_properties_add_button(
            test_grp, f"test_{c}", f"Send {c}", _make_test_button_cb(c),
        )
    obs.obs_properties_add_group(
        props, "test", "Test commands", obs.OBS_GROUP_NORMAL, test_grp,
    )

    # Scene -> command mapping. Leaving as plain text so users can name
    # scenes however they want without a live source enumeration.
    scene_grp = obs.obs_properties_create()
    for c in COMMANDS:
        obs.obs_properties_add_text(
            scene_grp, f"scene_{c}", f"Scene that triggers {c}",
            obs.OBS_TEXT_DEFAULT,
        )
    obs.obs_properties_add_group(
        props, "scene_mapping", "Scene → Command",
        obs.OBS_GROUP_NORMAL, scene_grp,
    )

    # Event -> command sequence. e.g. "STOP, REW" on RECORDING_STOPPED.
    event_grp = obs.obs_properties_create()
    obs.obs_properties_add_int(
        event_grp, "inter_command_ms",
        "Inter-command delay (ms)", 50, 5000, 50,
    )
    hint = obs.obs_properties_add_text(
        event_grp, "_event_hint",
        f"Comma-separated commands. Allowed: {', '.join(COMMANDS)}",
        obs.OBS_TEXT_INFO,
    )
    obs.obs_property_set_enabled(hint, False)
    for name, _ in _supported_events():
        obs.obs_properties_add_text(
            event_grp, f"event_{name}", name, obs.OBS_TEXT_DEFAULT,
        )
    obs.obs_properties_add_group(
        props, "event_mapping", "OBS Event → Command sequence",
        obs.OBS_GROUP_NORMAL, event_grp,
    )

    return props


def script_update(settings):
    port = obs.obs_data_get_string(settings, "port_path")
    if port != _state.get("port_path"):
        _state["port_path"] = port
        open_serial(port)

    _state["inter_command_ms"] = obs.obs_data_get_int(
        settings, "inter_command_ms") or DEFAULT_INTER_COMMAND_MS

    scene_mapping = {}
    for c in COMMANDS:
        scene = obs.obs_data_get_string(settings, f"scene_{c}").strip()
        if scene:
            scene_mapping[scene] = c
    _state["scene_commands"] = scene_mapping

    event_mapping = {}
    for name, _ in _supported_events():
        seq = parse_sequence(obs.obs_data_get_string(settings, f"event_{name}"))
        if seq:
            event_mapping[name] = seq
    _state["event_commands"] = event_mapping


def script_load(settings):
    _state["event_code_to_name"] = {code: name for name, code in _supported_events()}

    for c in COMMANDS:
        key_name = f"vcr_remote.{c}"
        hid = obs.obs_hotkey_register_frontend(
            key_name, f"VCR Remote: {c}", _make_hotkey_cb(c),
        )
        arr = obs.obs_data_get_array(settings, key_name)
        obs.obs_hotkey_load(hid, arr)
        obs.obs_data_array_release(arr)
        _state["hotkey_ids"][c] = hid

    obs.obs_frontend_add_event_callback(on_frontend_event)


def script_save(settings):
    for c, hid in _state["hotkey_ids"].items():
        arr = obs.obs_hotkey_save(hid)
        obs.obs_data_set_array(settings, f"vcr_remote.{c}", arr)
        obs.obs_data_array_release(arr)


def script_unload():
    close_serial()
