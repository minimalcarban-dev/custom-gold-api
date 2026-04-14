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
    """Primary source: actual IBJA Indian market gold rate"""
    try:
        url = "https://www.goodreturns.in/gold-rates/"
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.get(url, headers=headers, timeout=12)
        soup = BeautifulSoup(resp.text, "lxml")

        rates = {}
        for row in soup.select("table tr"):
            text = row.get_text(separator=" ", strip=True)
            nums = [
                float(n.replace(",", ""))
                for n in re.findall(r"[\d,]{5,}", text)
            ]
            valid = [n for n in nums if 40000 < n < 300000]

            if re.search(r"22\s*k|22\s*carat", text, re.I) and valid:
                rates["22k_10g"] = valid[0]
            if re.search(r"24\s*k|24\s*carat", text, re.I) and valid:
                rates["24k_10g"] = valid[0]

        if "22k_10g" in rates and "24k_10g" in rates:
            g22 = rates["22k_10g"] / 10
            g24 = rates["24k_10g"] / 10
            return {
                "22k": {"per_gram": round(g22, 2),
                        "per_10g": round(g22 * 10, 2),
                        "per_tola": round(g22 * TOLA, 2)},
                "24k": {"per_gram": round(g24, 2),
                        "per_10g": round(g24 * 10, 2),
                        "per_tola": round(g24 * TOLA, 2)},
                "source": "goodreturns.in (IBJA rate)",
                "accuracy": "actual Indian market rate",
            }
    except Exception as e:
        print(f"Scraping failed: {e}")
    return None


def get_yfinance_rate():
    """Fallback: international spot price + India import duties"""
    gold_usd_oz = yf.Ticker("GC=F").fast_info.last_price
    usd_inr     = yf.Ticker("USDINR=X").fast_info.last_price

    intl_per_gram = (gold_usd_oz / TROY_OZ_TO_GRAM) * usd_inr

    # India duties (2024): customs 6% + AIDC 5% + SWS ~0.6% + GST 3%
    # Effective multiplier: ~1.15
    g24 = round(intl_per_gram * 1.15, 2)
    g22 = round(g24 * (22 / 24), 2)

    return {
        "22k": {"per_gram": g22,
                "per_10g": round(g22 * 10, 2),
                "per_tola": round(g22 * TOLA, 2)},
        "24k": {"per_gram": g24,
                "per_10g": round(g24 * 10, 2),
                "per_tola": round(g24 * TOLA, 2)},
        "gold_usd_per_oz": round(gold_usd_oz, 2),
        "usd_inr_rate": round(usd_inr, 4),
        "source": "Yahoo Finance (calculated)",
        "accuracy": "approx — intl spot + India duties",
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