import subprocess
import threading
import time
import os
import sys
from pynput import keyboard
from database import get_setting

# CONFIGURATION
last_activity = time.time()
command_in_progress = False
command_lock = threading.Lock()


def clear_pending_console_input():
    try:
        import msvcrt
        while msvcrt.kbhit():
            msvcrt.getwch()
    except Exception:
        pass

def reset_activity_timer():
    global last_activity
    last_activity = time.time()


def get_timeout_seconds():
    raw = get_setting("timeout_minutes", "10")
    try:
        minutes = int(str(raw).strip())
    except Exception:
        minutes = 10
    minutes = max(5, min(30, minutes))
    return minutes * 60

def monitor_timeout():
    """Shuts down after configured inactivity timeout."""
    while True:
        time.sleep(10)
        with command_lock:
            is_busy = command_in_progress
        if is_busy:
            continue
        timeout_seconds = get_timeout_seconds()
        if time.time() - last_activity > timeout_seconds:
            print("\n[!] AI-Study-Tool shutting down due to inactivity.")
            clear_pending_console_input()
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
            reset_activity_timer()
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

    elif command_type == "list_folders":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "list-folders"], "Showing folders"),
            daemon=True
        ).start()

    elif command_type == "cycle_folder":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "cycle-folder"], "Cycling folder"),
            daemon=True
        ).start()

    elif command_type == "create_folder":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "create-folder"], "Creating folder"),
            daemon=True
        ).start()

    elif command_type == "help_menu":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "help-menu"], "Showing help"),
            daemon=True
        ).start()

    else:
        with command_lock:
            command_in_progress = False

def on_exit():
    print("\n[!] Exiting AI-Study-Tool.")
    clear_pending_console_input()
    os._exit(0)

# Hotkey Map (Alt + Shift + Letter)
hotkeys_map = {
    '<alt>+<shift>+q': lambda: run_command("capture"),
    '<alt>+<shift>+a': lambda: run_command("answer"),
    '<alt>+<shift>+f': lambda: run_command("list_folders"),
    '<alt>+<shift>+r': lambda: run_command("cycle_folder"),
    '<alt>+<shift>+k': lambda: run_command("create_folder"),
    '<alt>+<shift>+h': lambda: run_command("help_menu"),
    '<alt>+<shift>+e': on_exit
}

print("👂 AI-Study-Tool is listening...")
print("  Alt + Shift + Q : Capture")
print("  Alt + Shift + A : Answer")
print("  Alt + Shift + F : Show folders")
print("  Alt + Shift + R : Rotate active folder")
print("  Alt + Shift + K : Create a folder")
print("  Alt + Shift + H : Help menu")
print("  Use 'python otto.py help-menu' for full command reference")
print("  Use 'python otto.py shell' for interactive text commands")
print("  Use 'python otto.py settings-show' to view display settings")
print("  Use 'python otto.py set-folder <name>' to set the active folder by name")
print("  Use 'python otto.py rename-folder <old> <new>' to rename")
print("  Alt + Shift + E : Exit")
print(f"  (Single command at a time | Auto-exit: {get_timeout_seconds() // 60}m)")

threading.Thread(target=monitor_timeout, daemon=True).start()

with keyboard.GlobalHotKeys(hotkeys_map) as h:
    h.join()