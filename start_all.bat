@echo off
REM One-click launcher. stream.py now starts ffmpeg itself, so this just
REM runs the Python script in this window.
REM
REM While it's running:
REM   'r' + Enter  reconnect the cast (if the stream broke)
REM   'q' + Enter  shut everything down cleanly (ffmpeg, server, cast)
REM   Ctrl+C       same as 'q'

python "%~dp0stream.py"
