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
CAMERA_DEVICE    = "/dev/video0"
SNAPSHOT_PATH    = "/tmp/doorbell.jpg"
REFERENCE_PATH   = "/tmp/doorbell_reference.jpg"
# Minimum fraction of image that must change AND form a person-sized blob
MIN_CHANGE       = 0.04   # 4% of pixels changed
MIN_BLOB_AREA    = 0.04   # largest blob must cover at least 4% of image
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


def capture_image(path):
    """Capture a photo from the webcam to the given path."""
    subprocess.run(
        ["fswebcam", "-d", CAMERA_DEVICE, "-r", "640x480",
         "--no-banner", "-q", path],
        check=True, timeout=10
    )
    subprocess.run(
        ["convert", "-rotate", "-90", path, path],
        check=True, timeout=5
    )


def update_reference():
    """Save a background reference image (no person present)."""
    capture_image(REFERENCE_PATH)
    print("Reference background updated.")


def detect_person_and_blur(snapshot_path):
    """
    Returns True if a person-sized object appeared vs the background reference.
    Also blurs the background in the snapshot for privacy (hides street/neighbours).
    """
    try:
        import cv2
        img = cv2.imread(snapshot_path)
        ref = cv2.imread(REFERENCE_PATH)
        if img is None or ref is None:
            return True

        total = img.shape[0] * img.shape[1]

        # Compute difference mask
        gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        gray_ref = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(gray_img, gray_ref)
        _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

        # Clean up noise with morphology
        kernel = np.ones((20, 20), np.uint8)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel)

        changed_ratio = cv2.countNonZero(thresh) / total

        # Find the largest contour (blob)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            print(f"No change detected ({changed_ratio:.1%})")
            return False

        largest = max(contours, key=cv2.contourArea)
        blob_ratio = cv2.contourArea(largest) / total

        print(f"Change: {changed_ratio:.1%}, largest blob: {blob_ratio:.1%}")

        if changed_ratio < MIN_CHANGE or blob_ratio < MIN_BLOB_AREA:
            print("Too small — ignoring (not a person)")
            return False

        # Blur background for privacy — keep only the person's bounding box sharp
        x, y, w, h = cv2.boundingRect(largest)
        pad = 40
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(img.shape[1], x + w + pad)
        y2 = min(img.shape[0], y + h + pad)

        blurred = cv2.GaussianBlur(img, (61, 61), 0)
        blurred[y1:y2, x1:x2] = img[y1:y2, x1:x2]   # restore person area sharp

        cv2.imwrite(snapshot_path, blurred)
        print("Person detected, background blurred.")
        return True

    except Exception as e:
        print(f"Detection error: {e}")
        return True


def take_snapshot():
    """Capture doorbell photo. Returns True on success."""
    try:
        capture_image(SNAPSHOT_PATH)
        return True
    except Exception as e:
        print(f"Camera error: {e}")
        return False


def send_notification():
    try:
        if not take_snapshot():
            print("Camera failed, skipping notification.")
            return
        if not detect_person_and_blur(SNAPSHOT_PATH):
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
        # Take initial background reference
        try:
            update_reference()
        except Exception as e:
            print(f"Warning: could not take reference image: {e}")
    print("Press Ctrl+C to stop.\n")

    last_detected = 0
    last_reference = time.time()

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

                # Refresh background reference every hour
                if time.time() - last_reference > 3600:
                    try:
                        update_reference()
                        last_reference = time.time()
                    except Exception:
                        pass

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
