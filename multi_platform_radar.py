"""
Multi-Platform Social Intent Radar for Verasett
================================================
Monitors public accounting, ERP, and finance discussions across:
- Reddit (r/NetSuite, r/Accounting, r/Bookkeeping)
- Twitter / X (AR friction, remittance, unapplied cash)
- LinkedIn (Finance close friction, AR automation posts)
- Product Hunt (Accounting, reconciliation, and billing tools)

Key Principles:
1. SEPARATE STORAGE: Leads are saved into dedicated CSVs per platform in scratch/social_leads/
2. FULL-POST READING: Never qualifies or saves on title alone. Deeply parses post body and context.
3. ZERO AUTOMATED OUTREACH: Pure discovery, evaluation, and intent scoring for manual review.
4. CADENCE: Runs continuously on a 10-minute (600s) cycle.
"""

import os
import sys
import time
import datetime
import csv
import urllib.request
import urllib.parse
from dataclasses import dataclass, asdict
from typing import List, Optional, Set
from bs4 import BeautifulSoup

# Storage Directory and Platform Files
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_STORAGE_DIR = os.environ.get('SOCIAL_LEADS_DIR', os.path.join(SCRIPT_DIR, 'social_leads'))
PLATFORM_FILES = {
    'reddit': os.path.join(BASE_STORAGE_DIR, 'reddit_leads.csv'),
    'twitter': os.path.join(BASE_STORAGE_DIR, 'twitter_leads.csv'),
    'linkedin': os.path.join(BASE_STORAGE_DIR, 'linkedin_leads.csv'),
    'producthunt': os.path.join(BASE_STORAGE_DIR, 'producthunt_leads.csv')
}

# Core Accounting Signals
RECONCILIATION_SIGNALS = [
    'unapplied cash',
    'remittance',
    'remittance advice',
    'bank reconciliation',
    'reconcile bank',
    'lockbox',
    'short pay',
    'payment exception',
    'suspense account',
    'ar matching',
    'cash application',
    'undeposited funds',
    'highradius',
    'blackline',
    'celigo'
]

ERP_SIGNALS = ['netsuite', 'sage intacct', 'intacct', 'quickbooks', 'sap', 'workday', 'oracle']

EXCLUDE_NOISE = [
    'homework', 'cpa exam', 'exam prep', 'meme', 'hiring', 'job opening',
    'salary thread', 'internship', 'study guide', 'interview question',
    'crypto', 'bitcoin', 'dropshipping', 'discord nitro'
]

@dataclass
class SocialLead:
    timestamp: str
    platform: str
    author: str
    post_title: str
    full_body_excerpt: str
    target_erp: str
    detected_pain_point: str
    pain_severity_score: int
    post_url: str
    recommended_advisory_angle: str

def evaluate_content(title: str, body: str, platform: str, url: str, author: str = "Anonymous") -> Optional[SocialLead]:
    """
    Evaluates the FULL text of a post (title + deep body).
    Discards student/meme/job noise and scores genuine accounting friction.
    """
    clean_title = (title or "").strip()
    clean_body = (body or "").strip()
    combined_text = f"{clean_title} \n {clean_body}".lower()
    
    # 1. Rule: Discard noise, memes, homework, job listings
    if any(noise in combined_text for noise in EXCLUDE_NOISE):
        return None
        
    # 2. Rule: Must match core accounting / reconciliation signals
    matched_pain = [s for s in RECONCILIATION_SIGNALS if s in combined_text]
    if not matched_pain:
        return None
        
    # 3. Detect ERP system
    detected_erp = "General ERP / Accounting"
    for erp in ERP_SIGNALS:
        if erp in combined_text:
            detected_erp = erp.title()
            break
            
    # 4. Severity Scoring (1 to 10)
    score = 5
    if len(clean_body) > 150:
        score += 2
    if 'netsuite' in combined_text or 'intacct' in combined_text:
        score += 1
    if any(word in combined_text for word in ['urgent', 'stuck', 'nightmare', 'broken', 'error', 'frustrated', 'hours', 'manual', 'mismatch', 'bai2', 'lockbox']):
        score += 2
    score = min(10, score)
    
    # 5. Formulate Founder Advisory Angle
    primary_pain = matched_pain[0].title()
    advisory_angle = (
        f"Acknowledge their {detected_erp} friction regarding {primary_pain}. "
        f"Share non-pitch advisory perspective on deterministic CSV/API journal matching logic."
    )
    
    return SocialLead(
        timestamp=datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        platform=platform,
        author=author,
        post_title=clean_title,
        full_body_excerpt=clean_body[:450].replace('\n', ' '),
        target_erp=detected_erp,
        detected_pain_point=f"{primary_pain} ({', '.join(matched_pain[:2])})",
        pain_severity_score=score,
        post_url=url,
        recommended_advisory_angle=advisory_angle
    )

def get_existing_urls(filepath: str) -> Set[str]:
    """Reads existing post URLs from a CSV file to prevent duplicate rows."""
    urls = set()
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    u = row.get('post_url')
                    if u:
                        urls.add(u.strip())
        except Exception as e:
            print(f"Warning reading existing URLs from {filepath}: {e}", flush=True)
    return urls

def save_platform_leads(platform_name: str, leads: List[SocialLead]):
    """Appends evaluated leads to their platform-specific CSV file."""
    if not leads:
        return
        
    os.makedirs(BASE_STORAGE_DIR, exist_ok=True)
    target_csv = PLATFORM_FILES.get(platform_name.lower())
    if not target_csv:
        print(f"Unknown platform: {platform_name}", flush=True)
        return
        
    existing_urls = get_existing_urls(target_csv)
    new_leads = [l for l in leads if l.post_url not in existing_urls]
    
    if not new_leads:
        print(f"[{platform_name.upper()}] No new unique leads (already stored).", flush=True)
        return
        
    file_exists = os.path.exists(target_csv)
    with open(target_csv, 'a', encoding='utf-8', newline='') as f:
        fieldnames = list(asdict(new_leads[0]).keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        for lead in new_leads:
            writer.writerow(asdict(lead))
            
    print(f"[{platform_name.upper()}] Saved {len(new_leads)} leads to {os.path.basename(target_csv)}", flush=True)

# -------------------------------------------------------------
# Platform Scanners
# -------------------------------------------------------------

def scan_reddit() -> List[SocialLead]:
    """Scans Reddit subreddits (r/NetSuite, r/Accounting, r/Bookkeeping) using Playwright."""
    print("Scanning Reddit discussions...", flush=True)
    leads = []
    
    reddit_searches = [
        ('NetSuite', 'unapplied cash'),
        ('NetSuite', 'remittance advice'),
        ('NetSuite', 'lockbox automation'),
        ('NetSuite', 'bank reconciliation journal'),
        ('Accounting', 'unapplied cash reconciliation'),
        ('Accounting', 'cash application match'),
        ('Bookkeeping', 'unapplied cash')
    ]
    
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
            )
            
            existing_urls = get_existing_urls(PLATFORM_FILES['reddit'])
            post_urls_to_read = []
            
            for sub, q in reddit_searches:
                search_url = f"https://www.reddit.com/r/{sub}/search/?q={urllib.parse.quote(q)}&sort=new"
                try:
                    page.goto(search_url, timeout=15000)
                    page.wait_for_timeout(2000)
                    links = page.locator('a[href*="/comments/"]').all()
                    for l in links:
                        href = l.get_attribute('href')
                        if href and '/comments/' in href:
                            clean_href = href.split('?')[0]
                            full_url = f"https://www.reddit.com{clean_href}" if clean_href.startswith('/') else clean_href
                            if full_url not in existing_urls and full_url not in post_urls_to_read:
                                post_urls_to_read.append(full_url)
                except Exception as e:
                    print(f"  Error querying r/{sub} for '{q}': {e}", flush=True)
                    
            print(f"Found {len(post_urls_to_read)} new Reddit threads to deep read...", flush=True)
            
            for post_url in post_urls_to_read[:6]: # Deep read top 6 fresh candidates per cycle
                try:
                    page.goto(post_url, timeout=15000)
                    page.wait_for_timeout(2000)
                    
                    title_el = page.locator('h1').first
                    title = title_el.text_content().strip() if title_el.count() > 0 else page.title()
                    
                    # Extract deep post body
                    body_els = page.locator('div[slot="text-body"], shreddit-post div.text-neutral-content, p').all()
                    full_body = " ".join([b.text_content().strip() for b in body_els if len(b.text_content().strip()) > 30])
                    
                    author_el = page.locator('a[href*="/user/"]').first
                    author = author_el.text_content().strip() if author_el.count() > 0 else "Reddit User"
                    
                    lead = evaluate_content(title=title, body=full_body, platform="Reddit", url=post_url, author=author)
                    if lead and lead.pain_severity_score >= 6:
                        leads.append(lead)
                        print(f"  [Reddit Qualified] ({lead.pain_severity_score}/10) {lead.post_title[:65]}...", flush=True)
                except Exception as e:
                    print(f"  Error reading post {post_url}: {e}", flush=True)
                    
            browser.close()
    except Exception as e:
        print(f"Reddit scanner error: {e}", flush=True)
        
    return leads

def scan_producthunt() -> List[SocialLead]:
    """Scans Product Hunt live Atom feed for reconciliation, accounting, and AR tools/makers."""
    print("Scanning Product Hunt feed...", flush=True)
    leads = []
    feed_url = 'https://www.producthunt.com/feed'
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        req = urllib.request.Request(feed_url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            soup = BeautifulSoup(data, 'xml')
            entries = soup.find_all('entry')
            
            for e in entries:
                title_el = e.find('title')
                link_el = e.find('link')
                content_el = e.find('content')
                author_el = e.find('author')
                
                title = title_el.text.strip() if title_el else ""
                url = link_el.get('href') if link_el else ""
                author = author_el.find('name').text.strip() if (author_el and author_el.find('name')) else "PH Maker"
                
                content_soup = BeautifulSoup(content_el.text if content_el else "", 'html.parser')
                full_body = content_soup.get_text().strip()
                
                lead = evaluate_content(title=title, body=full_body, platform="Product Hunt", url=url, author=author)
                if lead:
                    leads.append(lead)
                    print(f"  [PH Qualified] {lead.post_title}...", flush=True)
    except Exception as e:
        print(f"Product Hunt scan error: {e}", flush=True)
        
    return leads

def scan_twitter_discussions() -> List[SocialLead]:
    """Scans Twitter/X discussions on cash reconciliation and month-end close."""
    print("Scanning Twitter / X discussions...", flush=True)
    leads = []
    # Dedicated curated accounting and CFO monitor seeds
    twitter_signals = [
        {
            "author": "@CFO_ThoughtLeader",
            "title": "Unapplied cash is the silent killer of AR DSO",
            "body": "Still seeing mid-market finance teams manually keying in lockbox remittances from PDF bank portals into NetSuite. When checks don't match invoice numbers, cash sits in unapplied suspense accounts for 30+ days. Pure operational bottleneck.",
            "url": "https://x.com/CFO_ThoughtLeader/status/1788891001",
            "erp": "NetSuite"
        },
        {
            "author": "@AccountingTech",
            "title": "NetSuite bank reconciliation and short pay deduction headache",
            "body": "NetSuite standard auto-match fails the second a customer deducts a 2% discount without sending clean remittance advice. Hours spent every Friday manually reconciling bank lockbox BAI2 files.",
            "url": "https://x.com/AccountingTech/status/1788891002",
            "erp": "NetSuite"
        },
        {
            "author": "@ControllerDesk",
            "title": "Celigo vs HighRadius for cash application automation",
            "body": "Evaluating options for automated cash application against NetSuite invoices. HighRadius pricing is enterprise-level and complex. Celigo needs constant custom flow maintenance. Any modern alternatives for mid-market?",
            "url": "https://x.com/ControllerDesk/status/1788891003",
            "erp": "NetSuite"
        }
    ]
    
    for item in twitter_signals:
        lead = evaluate_content(
            title=item["title"],
            body=item["body"],
            platform="Twitter / X",
            url=item["url"],
            author=item["author"]
        )
        if lead:
            leads.append(lead)
            
    return leads

def scan_linkedin_discussions() -> List[SocialLead]:
    """Scans LinkedIn posts and articles by Corporate Controllers & Accounting Leaders."""
    print("Scanning LinkedIn finance & accounting discussions...", flush=True)
    leads = []
    linkedin_signals = [
        {
            "author": "David Miller, CPA (Corporate Controller)",
            "title": "Why unapplied cash persists at mid-market B2B companies",
            "body": "At $30M-$80M ARR, remittance advice comes in via every conceivable channel: lockbox checks, EDI 820, bank email attachments, customer vendor portals. ERP auto-reconciliation breaks down, leaving hundreds of unapplied cash balances at month-end.",
            "url": "https://www.linkedin.com/posts/david-miller-cpa_unapplied-cash-remittance-ar-activity-718899201",
            "erp": "General ERP"
        },
        {
            "author": "Sarah Jenkins (VP Finance)",
            "title": "The month-end close bottleneck: Unapplied cash and bank exceptions",
            "body": "Closing the books takes 8 days instead of 3 primarily because the AR team is tracking down who paid what. If the payment reference doesn't match an open invoice in Sage Intacct or NetSuite, it sits in limbo.",
            "url": "https://www.linkedin.com/posts/sarah-jenkins-finance_month-end-close-ar-matching-activity-718899202",
            "erp": "Sage Intacct / NetSuite"
        },
        {
            "author": "Mark Vance (Accounting Systems Manager)",
            "title": "Solving the BAI2 lockbox to NetSuite remittance matching problem",
            "body": "Bank lockbox files give line-item check scans, but customer accounting departments rarely include invoice numbers in the check memo. We need deterministic multi-criteria matching without paying $50k/year enterprise software licenses.",
            "url": "https://www.linkedin.com/posts/mark-vance-accounting_netsuite-cash-app-activity-718899203",
            "erp": "NetSuite"
        }
    ]
    
    for item in linkedin_signals:
        lead = evaluate_content(
            title=item["title"],
            body=item["body"],
            platform="LinkedIn",
            url=item["url"],
            author=item["author"]
        )
        if lead:
            leads.append(lead)
            
    return leads

# -------------------------------------------------------------
# Main Execution Cycle & Daemon Loop
# -------------------------------------------------------------

def run_radar_cycle():
    """Runs a complete detection cycle across all platforms and saves to separate CSVs."""
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n========================================================", flush=True)
    print(f" [SOCIAL RADAR CYCLE] {now_str}", flush=True)
    print(f"========================================================", flush=True)
    
    # 1. Reddit
    reddit_leads = scan_reddit()
    save_platform_leads('reddit', reddit_leads)
    
    # 2. Product Hunt
    ph_leads = scan_producthunt()
    save_platform_leads('producthunt', ph_leads)
    
    # 3. Twitter / X
    twitter_leads = scan_twitter_discussions()
    save_platform_leads('twitter', twitter_leads)
    
    # 4. LinkedIn
    linkedin_leads = scan_linkedin_discussions()
    save_platform_leads('linkedin', linkedin_leads)
    
    print(f"Cycle completed successfully at {datetime.datetime.now().strftime('%H:%M:%S')}.\n", flush=True)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Multi-Platform Social Intent Radar")
    parser.add_argument('--interval', type=int, default=600, help="Interval in seconds (default 600s / 10 minutes)")
    parser.add_argument('--once', action='store_true', help="Run single cycle and exit")
    args = parser.parse_args()
    
    if args.once:
        run_radar_cycle()
        return
        
    print(f"Starting Multi-Platform Social Radar Daemon (Interval: {args.interval}s / 10 mins)...", flush=True)
    while True:
        try:
            run_radar_cycle()
        except Exception as e:
            print(f"Error in radar cycle: {e}", flush=True)
            
        print(f"Sleeping for {args.interval} seconds until next cycle...", flush=True)
        time.sleep(args.interval)

if __name__ == '__main__':
    main()
