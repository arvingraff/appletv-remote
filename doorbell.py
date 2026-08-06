"""
Doorbell detector — listens via ReSpeaker mic, sends ntfy notification when doorbell rings.
Run on Pi: .venv-pi/bin/python3 doorbell.py
"""

import time
import requests
import numpy as np

NTFY_TOPIC    = "Finnhaugveien16Doorbell"
NTFY_URL      = f"https://ntfy.sh/{NTFY_TOPIC}"

# How loud before we consider it a doorbell (0-32767, higher = less sensitive)
THRESHOLD     = 3000
# Seconds to wait after detecting before detecting again (avoid spam)
COOLDOWN      = 10
# How many seconds of audio to sample each loop
CHUNK_SECONDS = 0.5

def send_notification():
    try:
        requests.post(NTFY_URL, headers={
            "Title": "🔔 Doorbell!",
            "Priority": "high",
            "Tags": "bell",
        }, data="Someone is at the door!", timeout=5)
        print("✅ Notification sent!")
    except Exception as e:
        print(f"⚠️ Failed to send notification: {e}")

def listen():
    try:
        import sounddevice as sd
    except ImportError:
        print("Installing sounddevice...")
        import subprocess
        subprocess.run(["pip", "install", "sounddevice"], check=True)
        import sounddevice as sd

    SAMPLE_RATE = 16000
    CHUNK_SIZE  = int(SAMPLE_RATE * CHUNK_SECONDS)

    print(f"🎤 Listening for doorbell (threshold={THRESHOLD})...")
    print(f"📱 Notifications → ntfy.sh/{NTFY_TOPIC}")
    print("Press Ctrl+C to stop.\n")

    last_detected = 0

    while True:
        audio = sd.rec(CHUNK_SIZE, samplerate=SAMPLE_RATE, channels=1,
                       dtype="int16", blocking=True)
        volume = np.abs(audio).mean()

        if volume > THRESHOLD:
            now = time.time()
            if now - last_detected > COOLDOWN:
                print(f"🔔 Doorbell detected! (volume={volume:.0f})")
                send_notification()
                last_detected = now
            else:
                print(f"   (cooldown, volume={volume:.0f})")

if __name__ == "__main__":
    listen()
