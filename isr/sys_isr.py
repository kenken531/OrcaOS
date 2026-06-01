"""
OrcaOS — SysISR
Polls psutil every second and pushes readings to sys_queue.
No external hardware required — always runs.
"""
import time
import threading

import psutil

import state as _state

_start_time = time.monotonic()


def _sys_loop(stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            cpu    = psutil.cpu_percent(interval=None)
            ram    = psutil.virtual_memory().percent
            uptime = int(time.monotonic() - _start_time)
            _state.sys_queue.put_nowait({
                "cpu_percent": cpu,
                "ram_percent": ram,
                "uptime_s":    uptime,
            })
        except Exception:
            pass
        time.sleep(1.0)


def start(stop_event: threading.Event) -> threading.Thread:
    t = threading.Thread(
        target=_sys_loop, args=(stop_event,),
        daemon=True, name="SysISR"
    )
    t.start()
    return t
