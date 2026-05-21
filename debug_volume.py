"""
OrcaOS — debug_volume.py
Run this directly to test pycaw volume control isolated from the TUI.
Shows exactly what works and what fails on your system.

Usage:
    python debug_volume.py
"""
import sys, time, platform
print(f"Python {sys.version}")
print(f"Platform: {platform.system()} {platform.release()}")
print()

# ── Step 1: import comtypes ───────────────────────────────────────────────────
print("Step 1: import comtypes...")
try:
    import comtypes
    print(f"  OK — comtypes {comtypes.__version__}")
except ImportError as e:
    print(f"  FAIL: {e}")
    print("  Fix: pip install comtypes")
    sys.exit(1)

# ── Step 2: import pycaw ──────────────────────────────────────────────────────
print("Step 2: import pycaw...")
try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    print("  OK")
except ImportError as e:
    print(f"  FAIL: {e}")
    print("  Fix: pip install pycaw")
    sys.exit(1)

# ── Step 3: CoInitialize ──────────────────────────────────────────────────────
print("Step 3: CoInitialize...")
try:
    comtypes.CoInitialize()
    print("  OK")
except Exception as e:
    print(f"  FAIL: {e}")

# ── Step 4: GetSpeakers ───────────────────────────────────────────────────────
print("Step 4: AudioUtilities.GetSpeakers()...")
try:
    devices = AudioUtilities.GetSpeakers()
    print(f"  OK — {devices}")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# ── Step 5: Activate ─────────────────────────────────────────────────────────
print("Step 5: devices.Activate(IAudioEndpointVolume)...")
print("  Note: pycaw 20230407+ wraps device — using ._dev to get COM object")
try:
    # New pycaw: GetSpeakers() returns AudioDevice wrapper, need ._dev
    device = getattr(devices, '_dev', devices)
    iface = device.Activate(IAudioEndpointVolume._iid_, comtypes.CLSCTX_ALL, None)
    print(f"  OK — {iface}")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# ── Step 6: QueryInterface ────────────────────────────────────────────────────
print("Step 6: QueryInterface(IAudioEndpointVolume)...")
try:
    volume = iface.QueryInterface(IAudioEndpointVolume)
    print(f"  OK — {volume}")
except Exception as e:
    print(f"  FAIL (trying cast fallback): {e}")
    try:
        from ctypes import cast, POINTER
        volume = cast(iface, POINTER(IAudioEndpointVolume))
        print(f"  Cast fallback OK — {volume}")
    except Exception as e2:
        print(f"  Cast also FAIL: {e2}")
        sys.exit(1)

# ── Step 7: GetMasterVolumeLevelScalar ───────────────────────────────────────
print("Step 7: GetMasterVolumeLevelScalar()...")
try:
    current = volume.GetMasterVolumeLevelScalar()
    print(f"  OK — current volume: {current:.4f} ({current*100:.1f}%)")
except Exception as e:
    print(f"  FAIL: {e}")
    sys.exit(1)

# ── Step 8: SetMasterVolumeLevelScalar ───────────────────────────────────────
print("Step 8: SetMasterVolumeLevelScalar() — will change volume temporarily...")
try:
    original = volume.GetMasterVolumeLevelScalar()

    # bump up by 10%
    test_vol = min(1.0, original + 0.10)
    print(f"  Setting {original*100:.1f}% -> {test_vol*100:.1f}%...")
    volume.SetMasterVolumeLevelScalar(test_vol, None)
    time.sleep(0.3)
    readback = volume.GetMasterVolumeLevelScalar()
    print(f"  Readback after set: {readback*100:.1f}%")

    if abs(readback - test_vol) < 0.02:
        print("  SET WORKED ✓")
    else:
        print(f"  SET DID NOT TAKE — readback {readback:.4f} != target {test_vol:.4f}")
        print("  Trying without GUID arg...")
        try:
            volume.SetMasterVolumeLevelScalar(test_vol)
            time.sleep(0.3)
            readback2 = volume.GetMasterVolumeLevelScalar()
            print(f"  Readback2: {readback2*100:.1f}%")
            if abs(readback2 - test_vol) < 0.02:
                print("  SET WITHOUT GUID WORKED ✓")
            else:
                print("  Still not working")
        except Exception as e3:
            print(f"  No-GUID also failed: {e3}")

    # restore
    time.sleep(0.5)
    volume.SetMasterVolumeLevelScalar(original, None)
    print(f"  Restored to {original*100:.1f}%")

except Exception as e:
    print(f"  FAIL: {e}")
    import traceback; traceback.print_exc()

print()
print("Done. If Step 8 worked, pycaw is fine.")
print("If it failed, the issue is permissions or audio endpoint.")