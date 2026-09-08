# Verasett Multi-Platform Social Intent Radar

Autonomous 24/7 intelligence monitor for **Verasett** (B2B SaaS for Accounts Receivable unapplied cash and remittance reconciliation).

## Capabilities
- **Platform Separation:** Dedicated CSVs per channel in `social_leads/` (`reddit_leads.csv`, `twitter_leads.csv`, `linkedin_leads.csv`, `producthunt_leads.csv`).
- **Deep-Reading Rule:** Never qualifies or acts on titles alone. Parses full post body, comments, and context. Discards memes, student homework, and job openings.
- **Zero Automated Outreach:** Pure persistence and high-integrity founder advisory scoring.
- **24/7 Cloud Automation:** GitHub Actions runs scans every 15 minutes and commits new qualified leads.
- **Live Dashboard:** Open `index.html` locally or deploy via GitHub Pages.

## Quick Start
```bash
pip install -r requirements.txt
python -m playwright install --with-deps chromium
python multi_platform_radar.py --once
```
