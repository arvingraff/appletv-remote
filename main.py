"""
LEGO NXT Robot Controller
Uses the nxt-python library to communicate with the NXT brick via USB or Bluetooth.

Hardware layout:
  Motor A  -> Back wheel
  Motor B  -> Front wheel
  Port S1  -> Touch sensor (bumper)
  Port S2  -> Camera / Color sensor
  Port S3  -> Sound sensor (ears)
  Port S4  -> Color sensor
"""

import nxt.locator
import nxt.sensor
from nxt.motor import Motor, Port
from nxt.sensor.generic import Sound, Touch, Color
import time


def connect_brick():
    """Connect to the NXT brick over USB or Bluetooth."""
    print("Searching for NXT brick (USB or Bluetooth)...")
    brick = nxt.locator.find()
    name, host, signal_strength, user_flash = brick.get_device_info()
    print(f"Connected to: {name}")
    if host:
        print(f"Connection type: Bluetooth ({host})")
    else:
        print("Connection type: USB")
    brick.play_tone_and_wait(440, 300)
    return brick


def move_forward(brick, speed: int = 80, duration: float = 1.0):
    """Drive both wheels forward."""
    motor_a = Motor(brick, Port.A)
    motor_b = Motor(brick, Port.B)
    motor_a.run(speed)
    motor_b.run(speed)
    time.sleep(duration)
    motor_a.brake()
    motor_b.brake()


def move_backward(brick, speed: int = 80, duration: float = 1.0):
    """Drive both wheels backward."""
    move_forward(brick, -speed, duration)


def turn_left(brick, speed: int = 75, duration: float = 0.5):
    """Spin left."""
    motor_a = Motor(brick, Port.A)
    motor_b = Motor(brick, Port.B)
    motor_a.run(-speed)
    motor_b.run(speed)
    time.sleep(duration)
    motor_a.brake()
    motor_b.brake()


def turn_right(brick, speed: int = 75, duration: float = 0.5):
    """Spin right."""
    motor_a = Motor(brick, Port.A)
    motor_b = Motor(brick, Port.B)
    motor_a.run(speed)
    motor_b.run(-speed)
    time.sleep(duration)
    motor_a.brake()
    motor_b.brake()


def stop(brick):
    """Stop both wheels immediately."""
    Motor(brick, Port.A).brake()
    Motor(brick, Port.B).brake()


def read_touch(brick) -> bool:
    """Read the touch sensor on S1."""
    return bool(Touch(brick, nxt.sensor.Port.S1).get_sample())


def read_sound(brick) -> float:
    """Read the sound sensor on S3."""
    return Sound(brick, nxt.sensor.Port.S3).get_sample()


def read_color(brick) -> int:
    """Read the color sensor on S4."""
    return Color(brick, nxt.sensor.Port.S4).get_sample()


def sound_activated_demo(brick):
    """Clap to go, touch bumper to stop."""
    print("\n🤖 Sound-activated demo running!")
    print("   👏 Clap to make it go   |   🖐  Touch bumper to stop")
    print("   Press Ctrl+C to quit\n")
    try:
        while True:
            if read_touch(brick):
                print("🖐  Bumper hit! Stopping.")
                stop(brick)
                brick.play_tone_and_wait(220, 400)
                time.sleep(0.5)

            loudness = read_sound(brick)
            print(f"🔊 Sound: {loudness:.0f}   ", end="\r")
            if loudness > 350:
                print(f"\n👏 Clap! ({loudness:.0f}) — Moving forward!")
                move_forward(brick, speed=80, duration=1.0)

            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n\nStopping robot. Goodbye! 👋")
        stop(brick)


def main():
    try:
        brick = connect_brick()
        print("✅ NXT brick connected!\n")
        print("  Motor A  → Back wheel")
        print("  Motor B  → Front wheel")
        print("  S1       → Touch sensor")
        print("  S2       → Camera / Color sensor")
        print("  S3       → Sound sensor")
        print("  S4       → Color sensor")
        sound_activated_demo(brick)
    except Exception as e:
        print(f"❌ Error: {e}")
        print("Make sure your NXT brick is on and connected via USB or Bluetooth.")


if __name__ == "__main__":
    main()
