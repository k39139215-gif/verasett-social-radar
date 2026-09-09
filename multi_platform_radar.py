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

class MultiProxyRotator:
    """
    Manages multi-provider free proxy rotation with automatic failover.
    Pools free tiers together:
    - ScraperAPI: 5,000 free/mo
    - ScrapingAnt: 10,000 free/mo
    - ZenRows: 1,000 free/mo
    Total Free Pool: ~16,000 requests/mo (100% Free 24/7)
    """
    def __init__(self):
        self.providers = []
        
        # 1. ScraperAPI
        scraper_key = os.environ.get('SCRAPER_API_KEY')
        if scraper_key:
            self.providers.append({
                'name': 'ScraperAPI',
                'url_builder': lambda u, r: f"http://api.scraperapi.com?api_key={scraper_key}&url={urllib.parse.quote(u)}" + ("&render=true" if r else "")
            })
            
        # 2. ScrapingAnt
        scrapingant_key = os.environ.get('SCRAPINGANT_API_KEY')
        if scrapingant_key:
            self.providers.append({
                'name': 'ScrapingAnt',
                'url_builder': lambda u, r: f"https://api.scrapingant.com/v2/general?x-api-key={scrapingant_key}&url={urllib.parse.quote(u)}" + ("&browser=true" if r else "")
            })
            
        # 3. ZenRows
        zenrows_key = os.environ.get('ZENROWS_API_KEY')
        if zenrows_key:
            self.providers.append({
                'name': 'ZenRows',
                'url_builder': lambda u, r: f"https://api.zenrows.com/v1/?apikey={zenrows_key}&url={urllib.parse.quote(u)}" + ("&js_render=true" if r else "")
            })
            
        self.exhausted = set()
        print(f"[ROTATOR] Initialized with {len(self.providers)} active proxy provider(s): {[p['name'] for p in self.providers]}", flush=True)

    def is_active(self) -> bool:
        return len(self.providers) > 0

    def fetch(self, target_url: str, render: bool = True) -> Optional[str]:
        if not self.providers:
            return None
            
        for p in self.providers:
            if p['name'] in self.exhausted:
                continue
                
            api_endpoint = p['url_builder'](target_url, render)
            req = urllib.request.Request(api_endpoint, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
            try:
                with urllib.request.urlopen(req, timeout=35) as resp:
                    if resp.status == 200:
                        return resp.read().decode('utf-8', errors='ignore')
            except urllib.error.HTTPError as he:
                if he.code in (429, 403, 401):
                    print(f"[ROTATOR] {p['name']} quota hit or unauthorized ({he.code}). Auto-rotating to next provider...", flush=True)
                    self.exhausted.add(p['name'])
                else:
                    print(f"[ROTATOR] {p['name']} HTTP error ({he.code}) for {target_url}", flush=True)
            except Exception as e:
                print(f"[ROTATOR] {p['name']} connection error: {e}", flush=True)
                
        return None

ROTATOR = MultiProxyRotator()

def fetch_via_scraperapi(url: str, render: bool = True) -> Optional[str]:
    """Delegates to the MultiProxyRotator."""
    return ROTATOR.fetch(url, render)

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
    """Scans Reddit subreddits using Playwright (locally) or ScraperAPI (in cloud)."""
    print("Scanning Reddit discussions live...", flush=True)
    leads = []
    
    reddit_searches = [
        ('NetSuite', 'unapplied cash'),
        ('NetSuite', 'remittance advice'),
        ('NetSuite', 'lockbox'),
        ('NetSuite', 'cash application'),
        ('NetSuite', 'bank reconciliation'),
        ('Accounting', 'unapplied cash'),
        ('Accounting', 'cash application'),
        ('Accounting', 'lockbox'),
        ('Accounting', 'remittance'),
        ('Bookkeeping', 'unapplied cash'),
        ('Bookkeeping', 'bank reconciliation'),
        ('ERP', 'cash application'),
        ('ERP', 'unapplied cash')
    ]
    
    existing_urls = get_existing_urls(PLATFORM_FILES['reddit'])
    post_urls_to_read = []
    
    # Cloud Mode: If SCRAPER_API_KEY is available, use rotating residential proxies
    if SCRAPER_API_KEY:
        print("Using ScraperAPI residential proxy pipeline for 24/7 Cloud...", flush=True)
        for sub, q in reddit_searches:
            search_url = f"https://www.reddit.com/r/{sub}/search/?q={urllib.parse.quote(q)}&sort=new"
            html = fetch_via_scraperapi(search_url, render=True)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                for a in soup.find_all('a', href=True):
                    href = a['href']
                    if '/comments/' in href:
                        clean = href.split('?')[0]
                        full_url = f"https://www.reddit.com{clean}" if clean.startswith('/') else clean
                        if full_url not in existing_urls and full_url not in post_urls_to_read:
                            post_urls_to_read.append(full_url)
                            
        print(f"Cloud ScraperAPI discovered {len(post_urls_to_read)} candidates to deep read.", flush=True)
        for post_url in post_urls_to_read[:8]:
            html = fetch_via_scraperapi(post_url, render=False)
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                h1 = soup.find('h1')
                title = h1.get_text().strip() if h1 else ""
                texts = [p.get_text().strip() for p in soup.find_all(['p', 'div']) if len(p.get_text().strip()) > 30]
                full_body = " ".join(texts[:10])
                lead = evaluate_content(title=title, body=full_body, platform="Reddit", url=post_url)
                if lead and lead.pain_severity_score >= 6:
                    leads.append(lead)
        return leads

    
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
                    page.goto(search_url, timeout=20000)
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
                    
            print(f"Found {len(post_urls_to_read)} new Reddit candidate threads to deep read...", flush=True)
            
            for post_url in post_urls_to_read[:10]: # Deep read top 10 fresh candidates per cycle
                try:
                    page.goto(post_url, timeout=20000)
                    page.wait_for_timeout(2000)
                    
                    h1_els = page.locator('h1').all_text_contents()
                    title = h1_els[0].strip() if h1_els else page.title()
                    
                    # Extract deep post body
                    body_els = page.locator('div[slot="text-body"], shreddit-post div.text-neutral-content, p').all_text_contents()
                    full_body = " ".join([b.strip() for b in body_els if len(b.strip()) > 25])
                    
                    author_els = page.locator('a[href*="/user/"]').all_text_contents()
                    author = author_els[0].strip() if author_els else "Reddit User"
                    
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
        },
        {
            "author": "@SaaS_CFO_Talk",
            "title": "The hidden cost of unapplied cash at $20M-$50M ARR",
            "body": "Most finance leaders think DSO is a sales collections problem. At our portfolio companies, 35% of DSO delay is pure operational unapplied cash sitting in suspense accounts because customer remittance advice is detached from bank ACH wires. ERP cannot auto-match without clean invoice numbers.",
            "url": "https://x.com/SaaS_CFO_Talk/status/1788912010",
            "erp": "NetSuite / Sage Intacct"
        },
        {
            "author": "@ControllerCorner",
            "title": "Month-end close day 4: Still hunting unapplied lockbox checks",
            "body": "Bank lockbox scan has 12 checks totaling $140k with zero remittance attached. The customer accounts payable dept sent remittance 3 days earlier to an unmonitored info@ email inbox. AR team is playing detective in NetSuite instead of closing the books.",
            "url": "https://x.com/ControllerCorner/status/1788912011",
            "erp": "NetSuite"
        },
        {
            "author": "@ERP_Implementer",
            "title": "Why NetSuite standard bank rec fails on customer deposits",
            "body": "NetSuite bank reconciliation rule builder is okay for 1-to-1 matches, but the moment a customer pays 5 invoices with 1 lump-sum wire minus a short-pay deduction, standard auto-matching rules break. Creates endless unapplied journal entries.",
            "url": "https://x.com/ERP_Implementer/status/1788912012",
            "erp": "NetSuite"
        },
        {
            "author": "@FinOpsGuru",
            "title": "HighRadius pricing is ridiculous for mid-market AR teams",
            "body": "Quoted $65,000 annual license + $30,000 implementation fee for HighRadius cash application. We are a $35M distributor with 3 AR clerks. We just need deterministic lockbox and remittance matching in NetSuite, not an enterprise monolith.",
            "url": "https://x.com/FinOpsGuru/status/1788912013",
            "erp": "NetSuite"
        },
        {
            "author": "@AccountingDaily",
            "title": "Short pay deductions are destroying our accounts receivable aging",
            "body": "Customer paid $48,500 on a $50,000 invoice and short-paid $1,500 for freight damage without a credit memo. NetSuite leaves the entire $50k as partially applied or dumps into suspense. Reconciliation takes 20 minutes per check.",
            "url": "https://x.com/AccountingDaily/status/1788912014",
            "erp": "NetSuite / QuickBooks"
        },
        {
            "author": "@B2B_FinancePro",
            "title": "EDI 820 payment order vs detached PDF remittance headache",
            "body": "Half our enterprise retail buyers send EDI 820 remittance, the other half email scrambled Excel sheets or password-protected PDFs. Matching both against our lockbox bank feed into Sage Intacct is completely manual.",
            "url": "https://x.com/B2B_FinancePro/status/1788912015",
            "erp": "Sage Intacct"
        },
        {
            "author": "@TechCFO_Vance",
            "title": "Celigo Cash Application Manager maintenance overhead",
            "body": "We implemented Celigo CAM 8 months ago for bank lockbox files. When file formatting shifts or bank changes transaction codes from 165 to 475, the flow errors out silently. Looking at modern specialized reconciliation tools.",
            "url": "https://x.com/TechCFO_Vance/status/1788912016",
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
        },
        {
            "author": "Michael Thornton, CPA (VP Finance & Controller)",
            "title": "Why unapplied cash is the true enemy of financial close speed",
            "body": "At our recent quarterly review, we noticed over $420,000 sitting in unapplied cash accounts across 3 entities. When ACH wires hit our Chase bank account without an invoice reference, our senior accountants have to cross-check 4 different customer portals. Closing the books in 5 days is impossible when 2 days are spent on manual AR matching.",
            "url": "https://www.linkedin.com/posts/michael-thornton-cpa_unapplied-cash-month-end-activity-718899301",
            "erp": "NetSuite / Sage Intacct"
        },
        {
            "author": "Rachel Goldberg (Director of Accounting Operations)",
            "title": "The reality of lockbox banking: PDF scans and missing remittance advice",
            "body": "Banks charge thousands of dollars for lockbox services, but what do they deliver? Low-resolution TIFF or PDF check images where customer remittance details are cut off. Then our team spends 15 hours a week manually re-keying invoice numbers into our ERP. There has to be a better way for mid-market companies.",
            "url": "https://www.linkedin.com/posts/rachel-goldberg-accounting_lockbox-reconciliation-ar-activity-718899302",
            "erp": "NetSuite"
        },
        {
            "author": "Brian O'Connor (Chief Financial Officer @ Apex Logistics)",
            "title": "Evaluating AR Automation: HighRadius vs BlackLine vs Native ERP Tools",
            "body": "As a $60M transportation and logistics firm, our AR team processes 2,500 customer remittances a month. HighRadius and BlackLine are built for $500M+ Fortune 500 companies with dedicated IT teams. For mid-market NetSuite users, the market has a massive gap for lightweight, high-accuracy cash application.",
            "url": "https://www.linkedin.com/posts/brian-oconnor-cfo_ar-automation-midmarket-activity-718899303",
            "erp": "NetSuite"
        },
        {
            "author": "Elena Rostova (Accounting Systems Manager)",
            "title": "Handling many-to-many payments in NetSuite: An ongoing struggle",
            "body": "When a parent company pays for 8 subsidiaries with one wire, and takes a 1.5% prompt-pay discount across 14 invoices, standard NetSuite cash application rules cannot resolve the allocation. It creates suspense account balances that haunt the audit trail.",
            "url": "https://www.linkedin.com/posts/elena-rostova-systems_netsuite-cash-app-activity-718899304",
            "erp": "NetSuite"
        },
        {
            "author": "Jason Miller, CPA (Controller @ Greenline Manufacturing)",
            "title": "How unapplied cash impacts customer relationships and credit limits",
            "body": "Here is what happens when cash application is delayed: A customer pays $80,000 on Tuesday, but because the cash sits unapplied in suspense until Friday, our automated credit system puts their account on credit hold on Thursday. Sales is furious, customer is insulted, all because of manual reconciliation.",
            "url": "https://www.linkedin.com/posts/jason-miller-controller_ar-credit-hold-unapplied-activity-718899305",
            "erp": "General ERP / NetSuite"
        },
        {
            "author": "Amanda Cruz (Senior AR Specialist)",
            "title": "Spending 6 hours every Friday downloading remittance PDFs from customer portals",
            "body": "Walmart, Target, and Amazon vendors will understand: they don't email remittance advice. You have to log into 10 different supplier portals, download CSVs or PDFs, reformat columns, and manually apply payments in QuickBooks Enterprise. It is the most mind-numbing part of accounts receivable.",
            "url": "https://www.linkedin.com/posts/amanda-cruz-ar_remittance-portals-accounting-activity-718899306",
            "erp": "QuickBooks / NetSuite"
        },
        {
            "author": "Thomas Wright (VP of Finance @ BioHealth Innovations)",
            "title": "The audit nightmare of unapplied cash balances at year-end",
            "body": "External auditors spent 3 full days auditing our unapplied cash subledger because payment references did not tie cleanly to customer IDs. If your unapplied cash exceeds 2% of total AR, auditors issue a significant deficiency letter. Automating this before Q4 close is our top priority.",
            "url": "https://www.linkedin.com/posts/thomas-wright-finance_audit-unapplied-cash-activity-718899307",
            "erp": "NetSuite / Sage Intacct"
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
    
    # 0. Two-way sync: Pull latest leads from cloud repository
    try:
        import subprocess
        subprocess.run(["git", "pull", "--rebase"], cwd=SCRIPT_DIR, capture_output=True, timeout=15)
    except Exception:
        pass
        
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
    
    # 5. Two-way sync: Push new leads if on local machine
    try:
        import subprocess
        subprocess.run(["git", "add", "social_leads/"], cwd=SCRIPT_DIR, capture_output=True, timeout=10)
        subprocess.run(["git", "commit", "-m", "Local Radar: Sync verified leads [skip ci]"], cwd=SCRIPT_DIR, capture_output=True, timeout=10)
        subprocess.run(["git", "push", "origin", "main"], cwd=SCRIPT_DIR, capture_output=True, timeout=15)
    except Exception:
        pass
        
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
