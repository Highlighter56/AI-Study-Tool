import subprocess
import threading
import time
import os
from pynput import keyboard

# CONFIGURATION
TIMEOUT_SECONDS = 1800  # 30 minutes
last_activity = time.time()

def reset_timer():
    global last_activity
    last_activity = time.time()

def monitor_timeout():
    """Background thread that closes the listener after inactivity."""
    while True:
        time.sleep(10) # Check every 10 seconds
        elapsed = time.time() - last_activity
        if elapsed > TIMEOUT_SECONDS:
            print("\n[!] Otto Listener shutting down due to 30 minutes of inactivity.")
            # Hard exit to ensure all threads stop
            os._exit(0)

def on_capture():
    reset_timer()
    print("\n[!] Triggering Capture...")
    subprocess.run(["python", "otto.py", "capture"])

def on_answer():
    reset_timer()
    print("\n[!] Revealing Latest Answer...")
    subprocess.run(["python", "otto.py", "answer"])

# Define the hotkeys using the <ctrl>+<alt>+char syntax
# This is much more stable on Windows
hotkeys_map = {
    '<ctrl>+<alt>+q': on_capture,
    '<ctrl>+<alt>+a': on_answer
}

print("Otto is listening...")
print("Press Ctrl+Alt+Q to Capture.")
print("Press Ctrl+Alt+A to See Latest Answer.")
print(f"Auto-shutdown active: Script will close after 30 mins of inactivity.")

# Start the timeout monitor in a separate thread
timer_thread = threading.Thread(target=monitor_timeout, daemon=True)
timer_thread.start()

# Start the GlobalHotKeys listener
with keyboard.GlobalHotKeys(hotkeys_map) as h:
    h.join()