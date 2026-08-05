"""Run this on the Pi to pair with your Apple TV and get credentials."""
import asyncio
import pyatv

APPLE_TV_ID = "12:FD:8F:CE:56:74"

async def pair_protocol(device, protocol, name):
    print(f"\nPairing {name}…")
    pairing = await pyatv.pair(device, protocol, asyncio.get_event_loop())
    await pairing.begin()
    pin = input(f"  Enter PIN shown on Apple TV for {name}: ")
    pairing.pin(int(pin.strip()))
    await pairing.finish()
    creds = pairing.service.credentials
    print(f"  ✅ {name} credentials: {creds}")
    await pairing.close()
    return creds

async def main():
    print("🔍 Scanning for Apple TV…")
    devices = await pyatv.scan(asyncio.get_event_loop(), identifier=APPLE_TV_ID)
    if not devices:
        print("❌ Apple TV not found! Make sure Pi and Apple TV are on the same network.")
        return

    device = devices[0]
    print(f"✅ Found: {device.name}")

    companion = await pair_protocol(device, pyatv.Protocol.Companion, "Companion")
    airplay   = await pair_protocol(device, pyatv.Protocol.AirPlay,   "AirPlay")

    print("\n" + "─"*60)
    print("Copy these into appletv_server.py:")
    print(f'\nCOMPANION_CREDENTIALS = "{companion}"')
    print(f'\nAIRPLAY_CREDENTIALS   = "{airplay}"')
    print("─"*60)

asyncio.run(main())
