import os
import shutil
import subprocess
import csv
import datetime
import sys

repo_dir = r"C:\Users\kartik\.gemini\antigravity\scratch\verasett-social-radar"
desktop_dir = r"C:\Users\kartik\Desktop\Verasett_Social_Leads"
log_file = os.path.join(desktop_dir, "auto_sync_history.log")

now_str = datetime.datetime.now().strftime("%Y-%m-%d %I:%M:%S %p")

try:
    # 1. Fetch & Hard Reset to GitHub Cloud commits
    subprocess.run(["git", "fetch", "origin", "main"], cwd=repo_dir, capture_output=True, timeout=30)
    subprocess.run(["git", "reset", "--hard", "origin/main"], cwd=repo_dir, capture_output=True, timeout=30)

    # 2. Copy all files to Desktop folder
    repo_leads = os.path.join(repo_dir, "social_leads")
    copied_files = 0
    if os.path.exists(repo_leads) and os.path.exists(desktop_dir):
        for fname in os.listdir(repo_leads):
            src = os.path.join(repo_leads, fname)
            dst = os.path.join(desktop_dir, fname)
            if os.path.isfile(src):
                shutil.copy2(src, dst)
                copied_files += 1

    # 3. Calculate total leads
    tot = 0
    for f in ['reddit_leads.csv', 'linkedin_leads.csv', 'twitter_leads.csv', 'producthunt_leads.csv']:
        fp = os.path.join(desktop_dir, f)
        if os.path.exists(fp):
            with open(fp, 'r', encoding='utf-8', errors='ignore') as cf:
                c = max(0, len(list(csv.reader(cf))) - 1)
                tot += c

    with open(log_file, "a", encoding="utf-8") as lf:
        lf.write(f"[{now_str}] SUCCESS: Synced {copied_files} files. Total Verified Leads: {tot}\n")
except Exception as e:
    with open(log_file, "a", encoding="utf-8") as lf:
        lf.write(f"[{now_str}] ERROR: {e}\n")
