import subprocess
import threading
import time
import sys
import os
from pynput import keyboard
from settings_utils import get_configured_timeout_seconds

# CONFIGURATION
last_activity = time.time()
command_in_progress = False
command_lock = threading.Lock()
shutdown_event = threading.Event()
listener_handle = None


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
    return get_configured_timeout_seconds()


def request_shutdown(message):
    if shutdown_event.is_set():
        return

    print(message)
    clear_pending_console_input()
    shutdown_event.set()

    if listener_handle is not None:
        listener_handle.stop()

def monitor_timeout():
    """Shuts down after configured inactivity timeout."""
    while not shutdown_event.is_set():
        time.sleep(10)
        with command_lock:
            is_busy = command_in_progress
        if is_busy:
            continue
        timeout_seconds = get_timeout_seconds()
        if time.time() - last_activity > timeout_seconds:
            request_shutdown("\n[!] AI-Study-Tool shutting down due to inactivity.")

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
            clear_pending_console_input()
            print(f"\n[!] {label}...")
            env = os.environ.copy()
            env["OTTO_RUN_MODE"] = "listener"
            result = subprocess.run(args, check=False, env=env)
            if result.returncode != 0:
                print(f"[!] {label} failed with exit code {result.returncode}.")
            reset_activity_timer()
        except Exception as exc:
            print(f"[!] {label} failed to start: {exc}")
        finally:
            clear_pending_console_input()
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
            args=([sys.executable, "otto.py", "folder-list"], "Showing folders"),
            daemon=True
        ).start()

    elif command_type == "cycle_folder":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "folder-cycle"], "Cycling folder"),
            daemon=True
        ).start()

    elif command_type == "create_folder":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "folder-create"], "Creating folder"),
            daemon=True
        ).start()

    elif command_type == "help_menu":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "help-menu"], "Showing help"),
            daemon=True
        ).start()

    elif command_type == "study_generate":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "study-generate"], "Generating study material"),
            daemon=True
        ).start()

    elif command_type == "feedback_yes":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "feedback-mark", "--type", "capture", "--status", "correct"], "Saving feedback (correct)"),
            daemon=True
        ).start()

    elif command_type == "feedback_no":
        threading.Thread(
            target=worker,
            args=([sys.executable, "otto.py", "feedback-mark", "--type", "capture", "--status", "incorrect", "--interactive"], "Saving feedback (incorrect)"),
            daemon=True
        ).start()

    else:
        with command_lock:
            command_in_progress = False

def on_exit():
    clear_pending_console_input()
    request_shutdown("\n[!] Exiting AI-Study-Tool.")
    time.sleep(0.05)
    clear_pending_console_input()

# Hotkey Map (Alt + Shift + Letter)
hotkeys_map = {
    '<alt>+<shift>+q': lambda: run_command("capture"),
    '<alt>+<shift>+a': lambda: run_command("answer"),
    '<alt>+<shift>+f': lambda: run_command("list_folders"),
    '<alt>+<shift>+r': lambda: run_command("cycle_folder"),
    '<alt>+<shift>+k': lambda: run_command("create_folder"),
    '<alt>+<shift>+g': lambda: run_command("study_generate"),
    '<alt>+<shift>+y': lambda: run_command("feedback_yes"),
    '<alt>+<shift>+x': lambda: run_command("feedback_no"),
    '<alt>+<shift>+h': lambda: run_command("help_menu"),
    '<alt>+<shift>+e': on_exit
}

print("👂 AI-Study-Tool is listening...")
print("  Alt + Shift + Q : Capture")
print("  Alt + Shift + A : Answer")
print("  Alt + Shift + F : Show folders")
print("  Alt + Shift + R : Rotate active folder")
print("  Alt + Shift + K : Create a folder")
print("  Alt + Shift + G : Generate study material")
print("  Alt + Shift + Y : Mark latest capture as correct")
print("  Alt + Shift + X : Mark latest capture as incorrect (with correction prompt)")
print("  Alt + Shift + H : Help menu")
print("  Use 'python otto.py help-menu' for full command reference")
print("  Use 'python otto.py shell' for interactive text commands")
print("  Use 'python otto.py settings-show' to view display settings")
print("  Use 'python otto.py folder-set <name>' to set the active folder by name")
print("  Use 'python otto.py folder-rename <old> <new>' to rename")
print("  Alt + Shift + E : Exit")
print(f"  (Single command at a time | Auto-exit: {get_timeout_seconds() // 60}m)")

threading.Thread(target=monitor_timeout, daemon=True).start()

with keyboard.GlobalHotKeys(hotkeys_map) as h:
    listener_handle = h
    h.join()