import os
import csv
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

p = r"C:\Users\kartik\Desktop\Verasett_Social_Leads"
arch_p = os.path.join(p, "archived_leads_older_than_1yr")

files = [
    ('Reddit', 'reddit_leads.csv', 'reddit_archived_older_than_1yr.csv'),
    ('LinkedIn', 'linkedin_leads.csv', 'linkedin_archived_older_than_1yr.csv'),
    ('Twitter / X', 'twitter_leads.csv', 'twitter_archived_older_than_1yr.csv'),
    ('Product Hunt', 'producthunt_leads.csv', 'producthunt_archived_older_than_1yr.csv')
]

print("  ========================================================")
print("   ACTIVE LEADS COUNT (< 1 YEAR OLD) ON YOUR DESKTOP:")
print("  ========================================================")
tot_active = 0
tot_archived = 0

for name, f, arch_f in files:
    fp = os.path.join(p, f)
    c_act = 0
    if os.path.exists(fp):
        with open(fp, 'r', encoding='utf-8', errors='ignore') as cf:
            c_act = max(0, len(list(csv.reader(cf))) - 1)
            tot_active += c_act
            
    c_arch = 0
    arch_fp = os.path.join(arch_p, arch_f)
    if os.path.exists(arch_fp):
        with open(arch_fp, 'r', encoding='utf-8', errors='ignore') as cf:
            c_arch = max(0, len(list(csv.reader(cf))) - 1)
            tot_archived += c_arch

    print(f"   * {name:15}: {c_act:,} Active (< 1 yr)  |  {c_arch:,} Archived (> 1 yr)")

print("  --------------------------------------------------------")
print(f"   >> TOTAL ACTIVE FRESH LEADS (< 1 YR) : {tot_active:,}")
print(f"   >> TOTAL ARCHIVED LEADS (> 1 YR)     : {tot_archived:,}")
print(f"   >> GRAND TOTAL IN SYSTEM             : {tot_active + tot_archived:,}")
print("  ========================================================")
