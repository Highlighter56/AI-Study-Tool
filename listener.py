import subprocess
import threading
import time
import os
import sys
from pynput import keyboard

# CONFIGURATION
TIMEOUT_SECONDS = 600   # 10 minutes
last_activity = time.time()
command_in_progress = False
command_lock = threading.Lock()

def reset_activity_timer():
    global last_activity
    last_activity = time.time()

def monitor_timeout():
    """Shuts down after 10 minutes of silence."""
    while True:
        time.sleep(10)
        if time.time() - last_activity > TIMEOUT_SECONDS:
            print("\n[!] AI-Study-Tool shutting down due to inactivity.")
            os._exit(0)

def run_command(command_type):
    global command_in_progress

    with command_lock:
        if command_in_progress:
            print("⏳ A command is already running... please wait for output.")
            return
        command_in_progress = True

    reset_activity_timer()

    def worker(args, label):
        global command_in_progress
        try:
            print(f"\n[!] {label}...")
            subprocess.run(args)
        finally:
            with command_lock:
                command_in_progress = False

    if command_type == "capture":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "capture"], "Capturing"),
            daemon=True
        ).start()

    elif command_type == "answer":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "answer"], "Revealing"),
            daemon=True
        ).start()

    else:
        with command_lock:
            command_in_progress = False

def on_exit():
    print("\n[!] Exiting AI-Study-Tool.")
    os._exit(0)

# Hotkey Map (Alt + Shift + Letter)
hotkeys_map = {
    '<alt>+<shift>+q': lambda: run_command("capture"),
    '<alt>+<shift>+a': lambda: run_command("answer"),
    '<alt>+<shift>+e': on_exit
}

print("👂 AI-Study-Tool is listening...")
print("  Alt + Shift + Q : Capture")
print("  Alt + Shift + A : Answer")
print("  Alt + Shift + E : Exit")
print("  (Single command at a time | Auto-exit: 10m)")

threading.Thread(target=monitor_timeout, daemon=True).start()

with keyboard.GlobalHotKeys(hotkeys_map) as h:
    h.join()