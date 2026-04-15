from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timezone
import requests, re, yfinance as yf
from bs4 import BeautifulSoup

app = FastAPI(title="India Gold Rate API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

TROY_OZ_TO_GRAM = 31.1035
TOLA = 11.6638   # grams per tola

def scrape_goodreturns():
    """Goodreturns homepage ticker se rate lo — reliable method"""
    try:
        url = "https://www.goodreturns.in/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=12)
        soup = BeautifulSoup(resp.text, "lxml")

        # Goodreturns ticker mein exactly "22k Gold ₹ 13,975/gm" format hota hai
        rate_22k = None
        for tag in soup.find_all(string=re.compile(r'22k\s*Gold', re.I)):
            match = re.search(r'[\d,]+', tag.parent.get_text())
            if match:
                rate_22k = float(match.group().replace(',', ''))
                break

        # Agar ticker se nahi mila toh page mein dhundo
        if not rate_22k:
            for tag in soup.find_all(string=re.compile(r'[\d]{4,5}')):
                text = tag.parent.get_text(strip=True)
                if '22' in text:
                    match = re.search(r'(\d{4,6})', text.replace(',',''))
                    if match:
                        val = float(match.group())
                        if 8000 < val < 25000:
                            rate_22k = val
                            break

        if rate_22k:
            # 24K = 22K / 0.9167 (purity ratio)
            rate_24k = round(rate_22k / (22/24), 2)
            g22, g24 = rate_22k, rate_24k
            return {
                "22k": {
                    "per_gram": g22,
                    "per_10g": round(g22 * 10, 2),
                    "per_tola": round(g22 * TOLA, 2)
                },
                "24k": {
                    "per_gram": g24,
                    "per_10g": round(g24 * 10, 2),
                    "per_tola": round(g24 * TOLA, 2)
                },
                "source": "goodreturns.in (IBJA rate)",
                "accuracy": "actual Indian market rate",
            }
    except Exception as e:
        print(f"Scraping error: {e}")
    return None


def get_yfinance_rate():
    """Fallback: international spot price + India 2026 import duties"""
    # 1. Get Live Data
    gold_usd_oz = yf.Ticker("GC=F").fast_info.last_price
    usd_inr     = yf.Ticker("USDINR=X").fast_info.last_price

    # 2. Convert to Base INR per Gram
    intl_per_gram = (gold_usd_oz / TROY_OZ_TO_GRAM) * usd_inr

    # 3. Apply 2026 Duties
    # Total Import Duty (BCD 5% + AIDC 1%) = 6%
    # GST on the landed cost = 3%
    # Effective tax = 1.06 (Import) * 1.03 (GST) = 1.0918
    INDIA_DUTY_MULTIPLIER = 1.0918 
    
    g24 = round(intl_per_gram * INDIA_DUTY_MULTIPLIER, 2)
    g22 = round(g24 * (22 / 24), 2)

    return {
        "22k": {
            "per_gram": g22,
            "per_10g": round(g22 * 10, 2),
            "per_tola": round(g22 * TOLA, 2)
        },
        "24k": {
            "per_gram": g24,
            "per_10g": round(g24 * 10, 2),
            "per_tola": round(g24 * TOLA, 2)
        },
        "gold_usd_per_oz": round(gold_usd_oz, 2),
        "usd_inr_rate": round(usd_inr, 4),
        "source": "Yahoo Finance (2026 Duty Logic)",
        "accuracy": "9.18% total tax applied (6% Import + 3% GST)",
    }


@app.get("/gold")
def get_gold():
    data = scrape_goodreturns() or get_yfinance_rate()
    return {
        "status": "ok",
        "currency": "INR",
        "prices": {
            "22k": data["22k"],
            "24k": data["24k"],
        },
        "meta": {
            "source": data["source"],
            "accuracy": data["accuracy"],
            "note": "Excludes making charges & hallmarking fees",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

@app.get("/")
def root():
    return {"api": "India Gold Rate API", "usage": "/gold"}