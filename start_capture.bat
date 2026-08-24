@echo off
REM Run this FIRST, in its own window, and leave it running.
REM It captures your desktop and writes a live HLS stream to C:\stream.
REM Stop it with Ctrl+C when you're done casting.

if not exist "C:\stream" mkdir "C:\stream"

ffmpeg -y ^
  -f gdigrab -framerate 30 -i desktop ^
  -f lavfi -i anullsrc=channel_layout=stereo:sample_rate=44100 ^
  -vf scale=1920:1200 ^
  -c:v libx264 -preset ultrafast -tune zerolatency -profile:v high -level 4.1 -pix_fmt yuv420p -b:v 6M ^
  -c:a aac -b:a 128k ^
  -g 30 -sc_threshold 0 ^
  -f hls -hls_time 1 -hls_list_size 4 -hls_flags delete_segments+omit_endlist+independent_segments ^
  C:\stream\stream.m3u8
