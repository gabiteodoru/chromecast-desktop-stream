# chromecast-desktop-stream

Cast your Windows desktop to a Chromecast over your LAN — no third-party
apps, just `ffmpeg` and Python.

`ffmpeg` captures your screen and encodes it as a live HLS stream, a small
Python script serves that stream over HTTP and tells a Chromecast on your
network to play it. That's the whole stack.

## Latency

On my machine there's about a **5 second delay** between what's on screen
and what shows up on the Chromecast (this is inherent to HLS — segment
duration plus buffering, not something easily tuned away). That makes it a
poor fit for anything needing tight sync, but I've been using it as a
"delay cam" alongside OBS Studio — e.g. for gymnastics practice, so you
can watch your own move play back on a screen a few seconds after you did
it. If low latency matters for your use case, this probably isn't the
right tool.

## Requirements

- Windows
- [ffmpeg](https://ffmpeg.org/download.html) installed and on your `PATH`
- Python 3.8+
- `pip install pychromecast`
- A Chromecast (or Chromecast-compatible TV/device) on the same LAN as your PC

## Quick start

Double-click **`start_all.bat`**. It starts the ffmpeg capture, waits for
the stream to come up, then launches the Python caster, which discovers
Chromecasts on your network (auto-picking if there's only one) and starts
casting.

That's it — one window, one command.

## While it's running

Type into the console window:

| Key | Action |
|---|---|
| `r` + Enter | Reconnect/restart the cast session (useful if playback glitches or the TV drops the stream) |
| `q` + Enter | Shut everything down cleanly — stops the cast, the HTTP server, and ffmpeg, and deletes the leftover `.ts`/`.m3u8` files |
| Ctrl+C | Same as `q` |

## Files

- **`stream.py`** — does the real work: starts/stops ffmpeg as a managed
  subprocess, serves `C:\stream` over HTTP, discovers and casts to a
  Chromecast, and handles reconnect/shutdown.
- **`start_all.bat`** — one-click launcher, just runs `stream.py`.
- **`start_capture.bat`** — standalone ffmpeg capture script, kept around
  as a manual fallback if you want to run ffmpeg yourself outside of
  `stream.py` (e.g. for debugging capture settings).

## How it works

1. `stream.py` launches `ffmpeg` with `gdigrab` (Windows desktop capture)
   and encodes to H.264/AAC, writing a rolling HLS playlist + segments to
   `C:\stream`.
2. It serves that folder over HTTP (default port `8080`) with permissive
   CORS headers so the Chromecast can fetch it.
3. It detects your LAN IP, discovers Chromecasts via `pychromecast`, and
   sends a `play_media` command pointing at your own machine's stream URL.
4. On shutdown, it sends ffmpeg a graceful `q` over stdin (so the HLS
   files finalize properly), stops the HTTP server and cast session, and
   deletes the leftover stream files.

## Troubleshooting

- **Nothing found when discovering devices** — make sure your PC and the
  Chromecast are on the same network/subnet (not on separate VLANs or a
  guest Wi-Fi that isolates clients).
- **Stream stutters or lags** — lower `-framerate`, drop `-b:v`, or reduce
  the `scale=` resolution in the ffmpeg args at the top of `stream.py`.
- **ffmpeg not found** — confirm `ffmpeg -version` works from a plain
  `cmd.exe` window; if not, ffmpeg isn't on your `PATH`.

## Extending to macOS / Linux

This project is Windows-only today (the only Windows-specific piece is
the screen-capture *input* to ffmpeg — everything else in `stream.py` is
plain, portable Python). We don't have Mac or Linux hardware to build or
test this ourselves, but a port is a contained change if you want to send
a PR. Here's what would need to change:

### 1. The ffmpeg capture input

`stream.py` currently hardcodes this Windows-specific input:

```
-f gdigrab -framerate 30 -i desktop
```

Swap it based on `platform.system()`:

- **macOS** — use `avfoundation`:
  ```
  -f avfoundation -framerate 30 -i "1:0"
  ```
  Device indices (`"1:0"` = screen 1, audio device 0) vary per machine —
  run `ffmpeg -f avfoundation -list_devices true -i ""` to list them. macOS
  will also prompt for a Screen Recording permission grant on first run.

- **Linux (X11)** — use `x11grab`, which works out of the box on most X11
  desktops:
  ```
  -f x11grab -framerate 30 -i :0.0
  ```

- **Linux (Wayland)** — X11grab generally can't see the screen under
  Wayland compositors. You'd need a PipeWire-based capture instead (via
  `-f pipewire` or a portal/xdg-desktop-portal-based screencast setup),
  which is a meaningfully different capture path, not just a flag swap.

### 2. Audio input

The current Windows setup uses `anullsrc` (silent audio track) rather than
capturing real system audio. If real audio capture is desired per-platform:

- Windows: `dshow` with a loopback/virtual audio device
- macOS: `avfoundation` (same device as above, different index)
- Linux: `pulse` or `pipewire` audio source

### 3. Output/working directory

`STREAM_DIR` is hardcoded to `C:\stream`. Replace with something
OS-appropriate, e.g.:

```python
import tempfile
STREAM_DIR = os.path.join(tempfile.gettempdir(), "chromecast-stream")
```

### 4. Everything else just works

The HTTP server, LAN IP detection, Chromecast discovery/casting via
`pychromecast`, and the reconnect/shutdown input loop are all plain
Python and already cross-platform — no changes needed there.

**In short:** gate the ffmpeg input args (and optionally the audio args)
on `platform.system()`, pick a sane per-OS output directory, and the rest
of the tool should work unmodified.

## License

MIT — see [LICENSE](LICENSE).
