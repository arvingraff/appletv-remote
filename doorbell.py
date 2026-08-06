"""
Doorbell detector — listens via ReSpeaker mic, sends ntfy notification when doorbell rings.
Uses arecord (ALSA) directly to avoid PulseAudio dependency when running as systemd service.

Run normally:          .venv-pi/bin/python3 doorbell.py
Calibrate audio:       .venv-pi/bin/python3 doorbell.py --calibrate
Record doorbell sound: .venv-pi/bin/python3 doorbell.py --record-doorbell
  (ring your doorbell when prompted — saves a 3-second audio fingerprint)
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

# Melody fingerprint — record your exact doorbell sound with --record-doorbell
# Set MELODY_MATCH = False to disable (fall back to frequency/volume only)
MELODY_REFERENCE = "/home/arvingraff/appletv-remote/doorbell_sound.npy"
MELODY_MATCH     = False   # set True after running --record-doorbell
MELODY_SIMILARITY = 0.6    # 0-1, higher = stricter match
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


def melody_similarity(audio, reference):
    """Normalized cross-correlation between two audio clips (0=no match, 1=perfect)."""
    a = audio.astype(float)
    r = reference.astype(float)
    # Trim/pad to same length
    length = min(len(a), len(r))
    a, r = a[:length], r[:length]
    norm = np.linalg.norm(a) * np.linalg.norm(r)
    if norm == 0:
        return 0.0
    return float(np.dot(a, r) / norm)


def record_doorbell_reference(cmd, sample_rate, chunk_size, channels, bytes_per_chunk):
    """Record doorbell sound between two Enter presses and save as reference fingerprint."""
    print("\nRECORD MODE — press Enter to START recording, then Enter again to STOP...")
    input()
    print("Recording... (press Enter to stop)")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    chunks = []

    import threading
    stop_event = threading.Event()

    def wait_for_enter():
        input()
        stop_event.set()

    t = threading.Thread(target=wait_for_enter, daemon=True)
    t.start()

    while not stop_event.is_set():
        data = proc.stdout.read(bytes_per_chunk)
        if data:
            samples = np.frombuffer(data, dtype=np.int16).reshape(-1, channels)
            chunks.append(samples[:, 0])

    proc.terminate()
    if not chunks:
        print("Nothing recorded.")
        return
    recording = np.concatenate(chunks)
    np.save(MELODY_REFERENCE, recording)
    duration = len(recording) / sample_rate
    print(f"Saved {duration:.1f}s doorbell fingerprint to {MELODY_REFERENCE}")
    print("Now set MELODY_MATCH = True in doorbell.py and restart.")


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
    Returns True only if a human is detected by YOLOv8.
    Blurs everything outside the person's bounding box for privacy.
    """
    try:
        import cv2
        from ultralytics import YOLO

        img = cv2.imread(snapshot_path)
        if img is None:
            return True

        # Load YOLOv8 nano (downloads ~6MB on first run)
        model = YOLO("yolov8n.pt")
        results = model(snapshot_path, verbose=False)

        # Find person detections (class 0 = person) with confidence > 30%
        person_boxes = []
        for r in results:
            for box, cls, conf in zip(r.boxes.xyxy, r.boxes.cls, r.boxes.conf):
                if int(cls) == 0 and float(conf) > 0.3:
                    person_boxes.append([int(v) for v in box])

        if not person_boxes:
            print("No person detected by YOLO.")
            return False

        print(f"Person detected ({len(person_boxes)} person(s)).")

        # Blur entire image for privacy
        blurred = cv2.GaussianBlur(img, (61, 61), 0)

        # Restore sharp region around each detected person (tight crop, 15px padding)
        for x1, y1, x2, y2 in person_boxes:
            pad = 15
            px1 = max(0, x1 - pad)
            py1 = max(0, y1 - pad)
            px2 = min(img.shape[1], x2 + pad)
            py2 = min(img.shape[0], y2 + pad)
            blurred[py1:py2, px1:px2] = img[py1:py2, px1:px2]

        cv2.imwrite(snapshot_path, blurred)
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


def listen(calibrate=False, record_doorbell=False):
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

    if record_doorbell:
        record_doorbell_reference(cmd, SAMPLE_RATE, CHUNK_SIZE, CHANNELS, bytes_per_chunk)
        return

    # Load melody reference if enabled
    melody_ref = None
    if MELODY_MATCH:
        try:
            melody_ref = np.load(MELODY_REFERENCE)
            print(f"Melody fingerprint loaded ({len(melody_ref)} samples).")
        except Exception as e:
            print(f"Warning: could not load melody reference: {e}")

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
                    # Melody fingerprint match (if enabled)
                    if melody_ref is not None:
                        sim = melody_similarity(channel, melody_ref)
                        print(f"   melody similarity: {sim:.2f} (need {MELODY_SIMILARITY})")
                        if sim < MELODY_SIMILARITY:
                            print(f"   (ignored — sound doesn't match doorbell melody)")
                            continue

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
    record_doorbell = "--record-doorbell" in sys.argv
    listen(calibrate=calibrate, record_doorbell=record_doorbell)
