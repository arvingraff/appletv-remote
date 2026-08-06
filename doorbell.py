"""
Doorbell detector — listens via ReSpeaker mic, sends ntfy notification when doorbell rings.
Uses arecord (ALSA) directly to avoid PulseAudio dependency when running as systemd service.
Run on Pi: .venv-pi/bin/python3 doorbell.py
"""

import time
import subprocess
import numpy as np
import requests

NTFY_TOPIC    = "Finnhaugveien16Doorbell"
NTFY_URL      = f"https://ntfy.sh/{NTFY_TOPIC}"

# How loud before we consider it a doorbell (0-32767, higher = less sensitive)
THRESHOLD     = 3000
# Seconds to wait after detecting before detecting again (avoid spam)
COOLDOWN      = 10
# How many seconds of audio to sample each loop
CHUNK_SECONDS = 0.5
SAMPLE_RATE   = 16000

def send_notification():
    try:
        requests.post(NTFY_URL, headers={
            "Title": "Doorbell!",
            "Priority": "high",
            "Tags": "bell",
        }, data="Someone is at the door!", timeout=5)
        print("Notification sent!")
    except Exception as e:
        print(f"Failed to send notification: {e}")

def listen():
    CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_SECONDS)
    bytes_per_chunk = CHUNK_SIZE * 2  # 16-bit = 2 bytes per sample

    cmd = [
        "arecord",
        "-f", "S16_LE",
        "-r", str(SAMPLE_RATE),
        "-c", "1",
        "-t", "raw",
        "-q",   # quiet — suppress arecord status messages
        "-",
    ]

    print(f"Listening for doorbell (threshold={THRESHOLD})...")
    print(f"Notifications -> ntfy.sh/{NTFY_TOPIC}")
    print("Press Ctrl+C to stop.\n")

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    last_detected = 0

    try:
        while True:
            data = proc.stdout.read(bytes_per_chunk)
            if not data:
                break
            samples = np.frombuffer(data, dtype=np.int16)
            volume = np.abs(samples).mean()

            if volume > THRESHOLD:
                now = time.time()
                if now - last_detected > COOLDOWN:
                    print(f"Doorbell detected! (volume={volume:.0f})")
                    send_notification()
                    last_detected = now
                else:
                    print(f"   (cooldown, volume={volume:.0f})")
    finally:
        proc.terminate()

if __name__ == "__main__":
    listen()
