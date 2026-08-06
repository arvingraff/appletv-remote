"""
Doorbell detector — listens via ReSpeaker mic, sends ntfy notification when doorbell rings.
Uses arecord (ALSA) directly to avoid PulseAudio dependency when running as systemd service.

Run normally:       .venv-pi/bin/python3 doorbell.py
Calibrate mode:     .venv-pi/bin/python3 doorbell.py --calibrate
  (ring your doorbell and note the frequency + direction printed, then set values below)
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

# Frequency filter
DOORBELL_FREQ     = 434
FREQ_TOLERANCE    = 150   # Hz

# Camera snapshot on doorbell ring
CAMERA_DEVICE = "/dev/video0"
SNAPSHOT_PATH = "/tmp/doorbell.jpg"
# LEFT_CHANNELS / RIGHT_CHANNELS: which mic indices face left/right.
# Set DIRECTION_FILTER = False to disable, or tune channel indices after calibrating.
# Run --calibrate and clap from the left — note which side shows higher volume.
DIRECTION_FILTER  = True
LEFT_CHANNELS     = [0, 1]   # mic indices facing left (tuned via calibration)
RIGHT_CHANNELS    = [2, 3]   # mic indices facing right
# How much louder the left side must be vs right (1.2 = 20% louder)
DIRECTION_RATIO   = 1.2
FREQ_TOLERANCE    = 150   # Hz


def dominant_frequency(samples, sample_rate):
    """Return the loudest frequency (Hz) in the audio chunk."""
    fft = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / sample_rate)
    return freqs[np.argmax(fft)]


def detect_person(image_path):
    """Return True if a person is detected in the image."""
    try:
        import cv2
        img = cv2.imread(image_path)
        if img is None:
            return True  # if image can't be read, don't block notification
        hog = cv2.HOGDescriptor()
        hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())
        boxes, _ = hog.detectMultiScale(img, winStride=(8, 8), padding=(4, 4), scale=1.05)
        return len(boxes) > 0
    except Exception as e:
        print(f"Person detection error: {e}")
        return True  # if detection fails, don't block notification


def take_snapshot():
    """Capture a photo from the webcam. Returns True on success."""
    try:
        subprocess.run(
            ["fswebcam", "-d", CAMERA_DEVICE, "-r", "640x480",
             "--no-banner", "-q", SNAPSHOT_PATH],
            check=True, timeout=10
        )
        # Rotate 90° counter-clockwise to fix camera orientation
        subprocess.run(
            ["convert", "-rotate", "-90", SNAPSHOT_PATH, SNAPSHOT_PATH],
            check=True, timeout=5
        )
        return True
    except Exception as e:
        print(f"Camera error: {e}")
        return False


def send_notification():
    try:
        if not take_snapshot():
            print("Camera failed, skipping notification.")
            return
        if not detect_person(SNAPSHOT_PATH):
            print("No person detected, ignoring.")
            return
        headers = {
            "Title": "Doorbell!",
            "Priority": "high",
            "Tags": "bell",
            "Filename": "doorbell.jpg",
        }
        with open(SNAPSHOT_PATH, "rb") as f:
            requests.post(NTFY_URL, data=f, headers=headers, timeout=15)
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
                        left_vol  = np.abs(samples[:, LEFT_CHANNELS]).mean()
                        right_vol = np.abs(samples[:, RIGHT_CHANNELS]).mean()
                        ratio = left_vol / (right_vol + 1)
                        direction = "LEFT" if ratio > DIRECTION_RATIO else "RIGHT" if ratio < 1/DIRECTION_RATIO else "CENTER"
                        print(f"volume={volume:.0f}  freq={freq:.0f} Hz  left={left_vol:.0f}  right={right_vol:.0f}  -> {direction}")
                    continue

                if volume > THRESHOLD:
                    # Frequency check (skip if DOORBELL_FREQ is 0)
                    if DOORBELL_FREQ:
                        freq = dominant_frequency(channel, SAMPLE_RATE)
                        if abs(freq - DOORBELL_FREQ) > FREQ_TOLERANCE:
                            print(f"   (ignored — wrong freq {freq:.0f} Hz, expected {DOORBELL_FREQ} Hz)")
                            continue

                    # Direction check
                    if DIRECTION_FILTER:
                        left_vol  = np.abs(samples[:, LEFT_CHANNELS]).mean()
                        right_vol = np.abs(samples[:, RIGHT_CHANNELS]).mean()
                        ratio = left_vol / (right_vol + 1)
                        if ratio < DIRECTION_RATIO:
                            print(f"   (ignored — not from left, ratio={ratio:.2f})")
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
