import subprocess
import threading
import time
import os
from pynput import keyboard

# CONFIGURATION
TIMEOUT_SECONDS = 600   # 10 minutes
COOLDOWN_SECONDS = 5    # 5-second cooldown
last_activity = time.time()
last_trigger_time = 0

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
    global last_trigger_time
    
    # Cooldown logic
    elapsed = time.time() - last_trigger_time
    if elapsed < COOLDOWN_SECONDS:
        print(f"⏳ Cooldown active... wait {int(COOLDOWN_SECONDS - elapsed)}s.")
        return 

    last_trigger_time = time.time()
    reset_activity_timer()

    if command_type == "capture":
        print("\n[!] Capturing...")
        threading.Thread(target=subprocess.run, args=(["python", "otto.py", "capture"],)).start()
        
    elif command_type == "answer":
        print("\n[!] Revealing...")
        threading.Thread(target=subprocess.run, args=(["python", "otto.py", "answer"],)).start()

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
print(f"  (Cooldown: {COOLDOWN_SECONDS}s | Auto-exit: 10m)")

threading.Thread(target=monitor_timeout, daemon=True).start()

with keyboard.GlobalHotKeys(hotkeys_map) as h:
    h.join()