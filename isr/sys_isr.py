"""
OrcaOS — SysISR
Polls psutil every second and pushes readings to sys_queue.
No external hardware required — always runs.
"""
import time
import threading
import psutil

from state import sys_queue, update_state

_start_time = time.time()


def _sys_loop(stop_event: threading.Event):
    while not stop_event.is_set():
        try:
            cpu  = psutil.cpu_percent(interval=None)
            ram  = psutil.virtual_memory().percent
            uptime = int(time.time() - _start_time)

            sys_queue.put_nowait({
                "cpu_percent": cpu,
                "ram_percent": ram,
                "uptime_s":    uptime,
            })
        except Exception:
            pass
        time.sleep(1.0)


def start(stop_event: threading.Event):
    t = threading.Thread(target=_sys_loop, args=(stop_event,), daemon=True, name="SysISR")
    t.start()
    return t
