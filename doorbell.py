"""
Doorbell detector — listens via ReSpeaker mic, sends ntfy notification when doorbell rings.
Uses arecord (ALSA) directly to avoid PulseAudio dependency when running as systemd service.

Run normally:       .venv-pi/bin/python3 doorbell.py
Calibrate mode:     .venv-pi/bin/python3 doorbell.py --calibrate
  (ring your doorbell and note the frequency printed, then set DOORBELL_FREQ below)
"""

import sys
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

# Frequency filter — set DOORBELL_FREQ to your doorbell's tone (Hz) after calibrating.
# Set to 0 to disable frequency filtering (any loud sound triggers).
# FREQ_TOLERANCE: how many Hz above/below the target are accepted.
DOORBELL_FREQ     = 434   # e.g. 880 for a typical doorbell
FREQ_TOLERANCE    = 150   # Hz


def dominant_frequency(samples, sample_rate):
    """Return the loudest frequency (Hz) in the audio chunk."""
    fft = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / sample_rate)
    return freqs[np.argmax(fft)]


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


def listen(calibrate=False):
    CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_SECONDS)
    CHANNELS = 6  # ReSpeaker 4 Mic Array requires 6 channels
    bytes_per_chunk = CHUNK_SIZE * CHANNELS * 2  # 16-bit = 2 bytes per sample

    cmd = [
        "arecord",
        "-D", "plughw:ArrayUAC10,0",  # ReSpeaker by name (stable across reboots)
        "-f", "S16_LE",
        "-r", str(SAMPLE_RATE),
        "-c", str(CHANNELS),
        "-t", "raw",
        "-q",   # quiet — suppress arecord status messages
        "-",
    ]

    if calibrate:
        print("CALIBRATE MODE — ring your doorbell and note the frequency.")
        print("Then set DOORBELL_FREQ in doorbell.py to that value.\n")
    else:
        freq_info = f", freq={DOORBELL_FREQ}Hz±{FREQ_TOLERANCE}" if DOORBELL_FREQ else ", freq=any"
        print(f"Listening for doorbell (threshold={THRESHOLD}{freq_info})...")
        print(f"Notifications -> ntfy.sh/{NTFY_TOPIC}")
    print("Press Ctrl+C to stop.\n")

    last_detected = 0

    while True:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            while True:
                data = proc.stdout.read(bytes_per_chunk)
                if not data:
                    err = proc.stderr.read().decode(errors="replace").strip()
                    if err:
                        print(f"arecord error: {err}")
                    break
                samples = np.frombuffer(data, dtype=np.int16).reshape(-1, CHANNELS)
                channel = samples[:, 0]
                volume = np.abs(channel).mean()

                if calibrate:
                    if volume > THRESHOLD:
                        freq = dominant_frequency(channel, SAMPLE_RATE)
                        print(f"volume={volume:.0f}  dominant_freq={freq:.0f} Hz")
                    continue

                if volume > THRESHOLD:
                    # Frequency check (skip if DOORBELL_FREQ is 0)
                    if DOORBELL_FREQ:
                        freq = dominant_frequency(channel, SAMPLE_RATE)
                        if abs(freq - DOORBELL_FREQ) > FREQ_TOLERANCE:
                            print(f"   (ignored — wrong freq {freq:.0f} Hz, expected {DOORBELL_FREQ} Hz)")
                            continue

                    now = time.time()
                    if now - last_detected > COOLDOWN:
                        print(f"Doorbell detected! (volume={volume:.0f})")
                        send_notification()
                        last_detected = now
                    else:
                        print(f"   (cooldown, volume={volume:.0f})")
        finally:
            proc.terminate()

        if calibrate:
            break
        print("arecord stopped, retrying in 5 seconds...")
        time.sleep(5)


if __name__ == "__main__":
    calibrate = "--calibrate" in sys.argv
    listen(calibrate=calibrate)
