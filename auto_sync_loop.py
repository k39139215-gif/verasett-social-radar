import os
import shutil
import subprocess
import time
import sys

repo_dir = r"C:\Users\kartik\.gemini\antigravity\scratch\verasett-social-radar"
desktop_dir = r"C:\Users\kartik\Desktop\Verasett_Social_Leads"

def sync_cycle():
    try:
        # Pull latest from GitHub (suppress console window popup)
        no_window = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_dir, capture_output=True, timeout=25, creationflags=no_window)
        subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=repo_dir, capture_output=True, timeout=25, creationflags=no_window)

        repo_leads = os.path.join(repo_dir, "social_leads")
        if os.path.exists(repo_leads) and os.path.exists(desktop_dir):
            for fname in os.listdir(repo_leads):
                src = os.path.join(repo_leads, fname)
                dst = os.path.join(desktop_dir, fname)
                if os.path.isfile(src):
                    shutil.copy2(src, dst)
                elif os.path.isdir(src):
                    shutil.copytree(src, dst, dirs_exist_ok=True)
            print(f"[AUTO-SYNC] Synced latest leads to Desktop at {time.strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    except Exception as e:
        print(f"[AUTO-SYNC] Error: {e}", flush=True)

if __name__ == "__main__":
    print("[AUTO-SYNC DAEMON] Active! Syncing GitHub Cloud -> Desktop every 5 minutes...", flush=True)
    while True:
        sync_cycle()
        time.sleep(300) # Every 5 minutes
