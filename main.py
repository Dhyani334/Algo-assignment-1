# main.py - FINPULSE BACKEND WITH SQLITE DATABASE
import yfinance as yf
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import os

app = FastAPI()

# Allow frontend to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DATABASE SETUP ----------

DB_PATH = "finpulse.db"

def get_db_connection():
    """Create a connection to the SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_database():
    """Create tables if they don't exist"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create stocks table (current data)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stocks (
            ticker TEXT PRIMARY KEY,
            name TEXT,
            sector TEXT,
            price REAL,
            change_pct REAL,
            market_cap REAL,
            pe_ratio REAL,
            eps REAL,
            volume REAL,
            pb_ratio REAL,
            week52_high REAL,
            week52_low REAL,
            dividend_yield REAL,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create historical prices table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS historical_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT,
            date TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume REAL,
            UNIQUE(ticker, date)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized successfully")

# Run database initialization on startup
init_database()

# ---------- STOCK LIST ----------

STOCKS = [
    # ---------- Banking (6) ----------
    "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", 
    "KOTAKBANK.NS", "INDUSINDBK.NS",
    
    # ---------- Information Technology (5) ----------
    "TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "TECHM.NS",
    
    # ---------- Auto & Auto Ancillary (5) ----------
    "MARUTI.NS", "TATAMOTORS.NS", "M&M.NS", "HEROMOTOCO.NS", "BAJAJ-AUTO.NS",
    
    # ---------- FMCG (4) ----------
    "HINDUNILVR.NS", "ITC.NS", "NESTLEIND.NS", "BRITANNIA.NS",
    
    # ---------- Pharma (4) ----------
    "SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS",
    
    # ---------- Energy & Metals (5) ----------
    "RELIANCE.NS", "ONGC.NS", "TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS",
    
    # ---------- Capital Goods / Infrastructure (4) ----------
    "LT.NS", "SIEMENS.NS", "TITAN.NS", "ULTRACEMCO.NS",
    
    # ---------- Finance / NBFC (2) ----------
    "BAJFINANCE.NS", "HDFCLIFE.NS"
]

# ---------- API ENDPOINTS ----------

@app.get("/")
def root():
    return {"message": "FinPulse API is running with SQLite"}

@app.post("/refresh")
def refresh():
    """Fetch fresh data from Yahoo Finance and store in SQLite"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    data = []
    for ticker in STOCKS:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            
            # Get current data
            stock_data = {
                "ticker": ticker,
                "name": info.get("longName", ticker),
                "sector": info.get("sector", ""),
                "price": info.get("currentPrice", info.get("regularMarketPrice", 0)),
                "change_pct": info.get("regularMarketChangePercent", 0),
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE", 0),
                "eps": info.get("trailingEps", 0),
                "volume": info.get("volume", 0),
                "pb_ratio": info.get("priceToBook", 0),
                "week52_high": info.get("fiftyTwoWeekHigh", 0),
                "week52_low": info.get("fiftyTwoWeekLow", 0),
                "dividend_yield": info.get("dividendYield", 0)
            }
            data.append(stock_data)
            
            # Save current data to stocks table (UPSERT)
            cursor.execute('''
                INSERT OR REPLACE INTO stocks (
                    ticker, name, sector, price, change_pct, market_cap,
                    pe_ratio, eps, volume, pb_ratio, week52_high, week52_low, dividend_yield
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                stock_data["ticker"], stock_data["name"], stock_data["sector"],
                stock_data["price"], stock_data["change_pct"], stock_data["market_cap"],
                stock_data["pe_ratio"], stock_data["eps"], stock_data["volume"],
                stock_data["pb_ratio"], stock_data["week52_high"],
                stock_data["week52_low"], stock_data["dividend_yield"]
            ))
            
            # Get historical data (last 180 days)
            hist = stock.history(period="6mo")
            if not hist.empty:
                hist.reset_index(inplace=True)
                hist.rename(columns={
                    "Date": "date",
                    "Open": "open",
                    "High": "high",
                    "Low": "low",
                    "Close": "close",
                    "Volume": "volume"
                }, inplace=True)
                hist["date"] = hist["date"].dt.strftime("%Y-%m-%d")
                
                # Save historical data
                for _, row in hist.iterrows():
                    cursor.execute('''
                        INSERT OR REPLACE INTO historical_prices
                        (ticker, date, open, high, low, close, volume)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        ticker, row["date"], row["open"], row["high"],
                        row["low"], row["close"], row["volume"]
                    ))
            
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            # Add placeholder data if fetch fails
            data.append({
                "ticker": ticker,
                "name": ticker,
                "sector": "",
                "price": 0,
                "change_pct": 0,
                "market_cap": 0,
                "pe_ratio": 0,
                "eps": 0,
                "volume": 0,
                "pb_ratio": 0,
                "week52_high": 0,
                "week52_low": 0,
                "dividend_yield": 0
            })
    
    conn.commit()
    conn.close()
    return {"count": len(data), "message": f"Successfully refreshed {len(data)} stocks"}

@app.get("/stocks")
def get_stocks():
    """Get all stocks from the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM stocks ORDER BY ticker")
    rows = cursor.fetchall()
    conn.close()
    
    # Convert rows to list of dictionaries
    stocks = [dict(row) for row in rows]
    return {"stocks": stocks}

@app.get("/stocks/{ticker}")
def get_stock(ticker: str):
    """Get a specific stock by ticker"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM stocks WHERE ticker = ?", (ticker,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return dict(row)
    return {"error": "Stock not found"}

@app.get("/stocks/{ticker}/history")
def get_history(ticker: str, days: int = 180):
    """Get historical price data for a stock"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT date, open, high, low, close, volume 
        FROM historical_prices 
        WHERE ticker = ? 
        ORDER BY date DESC 
        LIMIT ?
    ''', (ticker, days))
    
    rows = cursor.fetchall()
    conn.close()
    
    # Convert to list of dicts and reverse to chronological order
    history = [dict(row) for row in rows]
    history.reverse()
    
    return {"history": history}

@app.get("/market-summary")
def get_summary():
    """Get market summary (top gainers/losers, averages)"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM stocks")
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        return {
            "total_companies_tracked": 0,
            "total_market_cap": 0,
            "average_pe_ratio": 0,
            "top_gainers": [],
            "top_losers": []
        }
    
    df = pd.DataFrame([dict(row) for row in rows])
    
    # Calculate metrics
    total_market_cap = df["market_cap"].sum()
    avg_pe = df[df["pe_ratio"] > 0]["pe_ratio"].mean()
    
    # Top gainers and losers (filter out stocks with 0 change)
    df_filtered = df[df["change_pct"] != 0]
    top_gainers = df_filtered.nlargest(5, "change_pct")[["ticker", "name", "change_pct"]].to_dict(orient="records")
    top_losers = df_filtered.nsmallest(5, "change_pct")[["ticker", "name", "change_pct"]].to_dict(orient="records")
    
    return {
        "total_companies_tracked": len(df),
        "total_market_cap": total_market_cap,
        "average_pe_ratio": round(avg_pe, 2) if avg_pe else 0,
        "top_gainers": top_gainers,
        "top_losers": top_losers
    }

# ---------- BONUS FEATURE: Filter by P/E ----------

@app.get("/stocks/filter/pe")
def filter_by_pe(min_pe: float = Query(0, description="Minimum P/E ratio"), 
                 max_pe: float = Query(100, description="Maximum P/E ratio")):
    """Bonus feature: Filter stocks by P/E ratio range"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT * FROM stocks 
        WHERE pe_ratio >= ? AND pe_ratio <= ?
        ORDER BY pe_ratio
    ''', (min_pe, max_pe))
    
    rows = cursor.fetchall()
    conn.close()
    
    stocks = [dict(row) for row in rows]
    return {"count": len(stocks), "stocks": stocks}

# ---------- NEWS ENDPOINT USING RSS (Most Reliable) ----------
import requests
import xml.etree.ElementTree as ET

@app.get("/stocks/{ticker}/news")
def get_company_news(ticker: str, limit: int = 10):
    symbol = ticker.replace(".NS", "").replace(".BO", "")
    
    # Get company name from DB
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM stocks WHERE ticker = ?", (ticker,))
    row = cursor.fetchone()
    conn.close()
    
    company_name = row["name"] if row else symbol
    
    try:
        # Use Bing News RSS (no API key, very stable)
        search_query = company_name.replace(" ", "+")
        url = f"https://www.bing.com/news/search?q={search_query}&format=rss"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Parse XML
        root = ET.fromstring(response.content)
        items = root.findall(".//item")
        
        news_items = []
        for item in items[:limit]:
            title = item.find("title").text if item.find("title") is not None else "No Title"
            link = item.find("link").text if item.find("link") is not None else "#"
            source = item.find("source").text if item.find("source") is not None else "Unknown"
            pub_date = item.find("pubDate").text if item.find("pubDate") is not None else ""
            
            news_items.append({
                "title": title,
                "link": link,
                "source": source,
                "time": pub_date
            })
        
        return {
            "ticker": ticker,
            "news": news_items,
            "count": len(news_items)
        }
    except Exception as e:
        print(f"RSS Error: {e}")
        return {
            "ticker": ticker,
            "news": [],
            "count": 0,
            "error": str(e)
        }
