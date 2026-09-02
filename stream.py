"""
Cast your Windows desktop to a Chromecast device.

Easiest way to run: double-click start_all.bat (or just run this script
directly with python). It starts ffmpeg itself, serves the resulting HLS
stream, and casts it to a Chromecast on your network.

While casting:
    'r' + Enter  reconnect/restart the cast session (e.g. if playback broke)
    'q' + Enter  shut everything down cleanly (ffmpeg, HTTP server, cast)
    Ctrl+C       same as 'q'

Requirements:
    pip install pychromecast
    ffmpeg on PATH

What this script does:
    1. Starts ffmpeg capturing the desktop to C:\\stream as an HLS stream.
    2. Figures out your PC's LAN IP automatically.
    3. Starts a local HTTP server over C:\\stream so the Chromecast can fetch
       the HLS files.
    4. Discovers Chromecasts on your network and lets you pick one (or
       auto-picks if there's only one).
    5. Tells the chosen Chromecast to play the stream.
"""

import http.server
import os
import socket
import subprocess
import sys
import threading
import time

import pychromecast

STREAM_DIR = r"C:\stream"
HTTP_PORT = 8080
PLAYLIST_NAME = "stream.m3u8"

FFMPEG_ARGS = [
    "ffmpeg", "-y",
    "-f", "gdigrab", "-framerate", "30", "-i", "desktop",
    "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
    "-vf", "scale=1920:1200",
    "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
    "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p", "-b:v", "6M",
    "-c:a", "aac", "-b:a", "128k",
    "-g", "30", "-sc_threshold", "0",
    "-f", "hls", "-hls_time", "1", "-hls_list_size", "4",
    "-hls_flags", "delete_segments+omit_endlist+independent_segments",
    os.path.join(STREAM_DIR, PLAYLIST_NAME),
]


def get_lan_ip():
    """Ask the OS which local IP it would use to reach the internet.
    Doesn't actually send data anywhere."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip


def start_ffmpeg():
    os.makedirs(STREAM_DIR, exist_ok=True)
    print("Starting ffmpeg capture...")
    proc = subprocess.Popen(
        FFMPEG_ARGS,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def cleanup_stream_files(stream_dir):
    try:
        for name in os.listdir(stream_dir):
            if name.endswith(".ts") or name.endswith(".m3u8"):
                try:
                    os.remove(os.path.join(stream_dir, name))
                except OSError:
                    pass
    except FileNotFoundError:
        pass


def stop_ffmpeg(proc):
    if proc.poll() is not None:
        return
    print("Stopping ffmpeg...")
    try:
        proc.stdin.write(b"q\n")
        proc.stdin.flush()
        proc.wait(timeout=5)
        return
    except Exception:
        pass
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        proc.kill()


def wait_for_playlist(playlist_path, timeout=30):
    print("Waiting for stream to start...")
    start = time.time()
    while not os.path.exists(playlist_path):
        if time.time() - start > timeout:
            return False
        time.sleep(0.5)
    return True


def start_http_server(stream_dir, port):
    handler_dir = stream_dir

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=handler_dir, **kwargs)

        def end_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            super().end_headers()

        def log_message(self, format, *args):
            pass  # quiet the server logs

    httpd = http.server.ThreadingHTTPServer(("0.0.0.0", port), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    print(f"Serving {stream_dir} on port {port}...")
    return httpd


def pick_chromecast():
    print("Discovering Chromecasts...")
    chromecasts, browser = pychromecast.get_chromecasts()

    if not chromecasts:
        print("No Chromecasts found on the network.")
        browser.stop_discovery()
        return None, browser

    if len(chromecasts) == 1:
        print(f"Found one device: {chromecasts[0].cast_info.friendly_name} (auto-selected)")
        return chromecasts[0], browser

    print("\nAvailable devices:")
    for i, cc in enumerate(chromecasts):
        print(f"  [{i}] {cc.cast_info.friendly_name}")

    while True:
        choice = input("\nPick a device number: ").strip()
        if choice.isdigit() and 0 <= int(choice) < len(chromecasts):
            return chromecasts[int(choice)], browser
        print("Invalid choice, try again.")


def main():
    playlist_path = os.path.join(STREAM_DIR, PLAYLIST_NAME)

    ffmpeg_proc = start_ffmpeg()
    if not wait_for_playlist(playlist_path):
        print(f"Timed out waiting for {playlist_path}. Is ffmpeg installed and on PATH?")
        stop_ffmpeg(ffmpeg_proc)
        cleanup_stream_files(STREAM_DIR)
        return

    ip = get_lan_ip()
    print(f"Local LAN IP: {ip}")

    httpd = start_http_server(STREAM_DIR, HTTP_PORT)

    cast, browser = pick_chromecast()
    if cast is None:
        httpd.shutdown()
        stop_ffmpeg(ffmpeg_proc)
        cleanup_stream_files(STREAM_DIR)
        return

    cast.wait()
    url = f"http://{ip}:{HTTP_PORT}/{PLAYLIST_NAME}"
    mc = cast.media_controller

    def start_playback():
        print(f"Casting {url} to {cast.cast_info.friendly_name}...")
        mc.play_media(url, "application/x-mpegURL")
        mc.block_until_active()

    start_playback()

    print("\nCasting. Type 'r' + Enter to reconnect, 'q' + Enter to shut down everything.")
    print("Ctrl+C also shuts everything down.")

    stop_flag = threading.Event()

    def input_watcher():
        while not stop_flag.is_set():
            try:
                cmd = input().strip().lower()
            except EOFError:
                return
            if cmd == "r":
                print("Reconnecting...")
                try:
                    mc.stop()
                except Exception as e:
                    print(f"(ignoring error while stopping: {e})")
                try:
                    start_playback()
                    print("Reconnected.")
                except Exception as e:
                    print(f"Reconnect failed: {e}")
            elif cmd == "q":
                stop_flag.set()

    watcher = threading.Thread(target=input_watcher, daemon=True)
    watcher.start()

    try:
        while not stop_flag.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        stop_flag.set()
        print("Shutting down...")

        def safe(step_name, fn):
            try:
                fn()
            except Exception as e:
                print(f"(ignoring error while {step_name}: {e})")

        safe("stopping cast session", mc.stop)
        safe("shutting down HTTP server", httpd.shutdown)
        safe("stopping Chromecast discovery", browser.stop_discovery)
        safe("stopping ffmpeg", lambda: stop_ffmpeg(ffmpeg_proc))
        safe("cleaning up stream files", lambda: cleanup_stream_files(STREAM_DIR))
        print("Done.")


if __name__ == "__main__":
    main()
