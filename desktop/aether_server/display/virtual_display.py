"""
AetherControl - Virtual X11 Display Manager

Creates and removes a virtual secondary X11 output using xrandr + the
X11 dummy driver (xf86-video-dummy) or a synthetic modeline approach.

This is an X11-only feature — Wayland support is a documented future item.
The module gracefully degrades (warns, does not crash) if xrandr or the
dummy driver is not available on the system.

Typical flow:
  1. create_virtual_display(width, height) → returns monitor index (e.g. 1)
  2. Point X11CaptureBackend.start(monitor=<index>) at the new output
  3. remove_virtual_display() when the session ends
"""

import asyncio
import logging
import re
import shutil
import subprocess
from typing import Optional

log = logging.getLogger("aether.display.virtual")

# The xrandr output name we assign to the virtual display
_VIRTUAL_OUTPUT_NAME = "AETHER-VIRT-1"
_VIRTUAL_MODE_NAME = "AetherVirt"

# Tracks whether we currently have a virtual display created
_current_mode_name: Optional[str] = None
_current_output: Optional[str] = None


def _xrandr_available() -> bool:
    return shutil.which("xrandr") is not None


def _run(cmd: list[str], *, timeout: int = 5) -> tuple[int, str, str]:
    """Run a command, return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError:
        return -1, "", f"{cmd[0]} not found"


def _compute_modeline(width: int, height: int, refresh: float = 60.0) -> dict:
    """
    Compute a CVT-style modeline for the requested resolution.
    Falls back to calling `cvt` if available; otherwise uses a rough formula.
    """
    if shutil.which("cvt"):
        rc, out, _ = _run(["cvt", str(width), str(height), str(int(refresh))])
        if rc == 0:
            # Parse the Modeline line from cvt output
            for line in out.splitlines():
                if line.strip().startswith("Modeline"):
                    parts = line.split()
                    # parts[1] = "\"NxN_60.00\"", rest = pixel clock + timings
                    mode_name = parts[1].strip('"')
                    timings = parts[2:]
                    return {"name": mode_name, "timings": timings}

    # Rough fallback (approximate, good enough for a dummy virtual output)
    pclk = round(width * height * refresh / 1_000_000, 2)
    hfp = int(width * 0.02)
    hbp = int(width * 0.05)
    hsync = int(width * 0.03)
    vfp = 4
    vbp = 20
    vsync = 5
    htotal = width + hfp + hsync + hbp
    vtotal = height + vfp + vsync + vbp
    mode_name = f"{width}x{height}_{int(refresh)}"
    timings = [
        str(pclk),
        str(width), str(width + hfp), str(width + hfp + hsync), str(htotal),
        str(height), str(height + vfp), str(height + vfp + vsync), str(vtotal),
    ]
    return {"name": mode_name, "timings": timings}


def _find_dummy_output() -> Optional[str]:
    """
    Find an existing disconnected output to repurpose, or the dummy driver output.
    Returns the xrandr output name (e.g. "DUMMY0" or "VGA-1") or None.
    """
    rc, out, _ = _run(["xrandr"])
    if rc != 0:
        return None

    # Prefer any output named DUMMY* or VIRTUAL*
    for line in out.splitlines():
        name = line.split()[0] if line.split() else ""
        if name and any(k in name.upper() for k in ("DUMMY", "VIRTUAL")):
            return name

    # Fall back to any disconnected output we can repurpose
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "disconnected":
            return parts[0]

    return None


def _get_primary_output_position() -> tuple[int, int]:
    """Return (x, y) position of the rightmost edge of the primary monitor."""
    rc, out, _ = _run(["xrandr"])
    if rc != 0:
        return (1920, 0)  # Reasonable default

    # Find primary monitor's geometry from xrandr output
    # Pattern: "connected primary 1920x1080+0+0"
    best_x = 0
    for line in out.splitlines():
        match = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", line)
        if match and "disconnected" not in line:
            w, h, x, y = (int(g) for g in match.groups())
            right_edge = x + w
            if right_edge > best_x:
                best_x = right_edge

    return (best_x, 0)


async def create_virtual_display(
    width: int,
    height: int,
    refresh: float = 60.0,
) -> Optional[int]:
    """
    Create a virtual X11 display extended to the right of the primary monitor.

    Returns the monitor index (0-based, for use with X11CaptureBackend.start()),
    or None if creation failed.
    """
    global _current_mode_name, _current_output

    if not _xrandr_available():
        log.error("xrandr not found — virtual display unavailable on this system")
        return None

    # Snap to even dimensions (required by H.264)
    width = width & ~1
    height = height & ~1

    # 1. Find a suitable output to use
    output = _find_dummy_output()
    if output is None:
        log.error(
            "No dummy/virtual xrandr output found. "
            "Install xf86-video-dummy and add 'Virtual' output to xorg.conf, "
            "or load the dummy kernel module."
        )
        return None

    log.info("Using xrandr output '%s' for virtual display %dx%d", output, width, height)

    # 2. Create a modeline
    mode_info = await asyncio.get_event_loop().run_in_executor(
        None, _compute_modeline, width, height, refresh
    )
    mode_name = f"{_VIRTUAL_MODE_NAME}_{width}x{height}"
    timings = mode_info["timings"]

    # 3. xrandr --newmode
    rc, _, err = _run(["xrandr", "--newmode", mode_name] + timings)
    if rc != 0 and "already exists" not in err:
        log.error("xrandr --newmode failed: %s", err.strip())
        return None

    # 4. xrandr --addmode
    rc, _, err = _run(["xrandr", "--addmode", output, mode_name])
    if rc != 0:
        log.error("xrandr --addmode failed: %s", err.strip())
        return None

    # 5. Position to the right of the primary monitor
    pos_x, pos_y = _get_primary_output_position()

    # 6. xrandr --output <name> --mode <mode> --pos <x>x<y>
    rc, _, err = _run([
        "xrandr",
        "--output", output,
        "--mode", mode_name,
        "--pos", f"{pos_x}x{pos_y}",
    ])
    if rc != 0:
        log.error("xrandr --output failed: %s", err.strip())
        return None

    _current_mode_name = mode_name
    _current_output = output

    # Discover which monitor index this maps to in mss
    monitor_index = _find_monitor_index(output, width, height, pos_x, pos_y)
    log.info(
        "Virtual display created: %s @ %dx%d+%d+%d (monitor index %s)",
        output, width, height, pos_x, pos_y, monitor_index,
    )
    return monitor_index


def _find_monitor_index(
    output: str,
    width: int,
    height: int,
    pos_x: int,
    pos_y: int,
) -> int:
    """
    Find the mss monitor index for the newly created virtual display.
    mss numbers monitors 1..N; 0 is the combined virtual screen.
    """
    try:
        import mss  # type: ignore[import]
        with mss.mss() as sct:
            for idx, mon in enumerate(sct.monitors):
                if idx == 0:
                    continue  # skip the "all monitors" entry
                if mon["left"] == pos_x and mon["top"] == pos_y:
                    if abs(mon["width"] - width) <= 2 and abs(mon["height"] - height) <= 2:
                        return idx - 1  # convert 1-based mss index to 0-based
    except Exception as exc:
        log.debug("mss monitor detection failed: %s", exc)

    # Fallback: assume the new display is the last one
    return 1


async def remove_virtual_display() -> None:
    """
    Remove the virtual display created by create_virtual_display().
    Safe to call even if no virtual display is active.
    """
    global _current_mode_name, _current_output

    if _current_output is None:
        return

    output = _current_output
    mode_name = _current_mode_name

    log.info("Removing virtual display on '%s'", output)

    # Turn off the output first
    _run(["xrandr", "--output", output, "--off"])

    if mode_name:
        # Remove the mode from the output, then delete the mode
        _run(["xrandr", "--delmode", output, mode_name])
        _run(["xrandr", "--rmmode", mode_name])

    _current_output = None
    _current_mode_name = None
    log.info("Virtual display removed")
