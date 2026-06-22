from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import sqlite3
import os
import random
import threading
import time
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

app = FastAPI(title="AI Trade Bridge API")

# HTML şablonları için klasör
templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
templates = Jinja2Templates(directory=templates_dir)

# CORS ayarları (Frontend'in API'ye erişebilmesi için)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Veritabanı Kurulumu
DB_PATH = '/data/ai_database.db' if os.path.exists('/data') else 'ai_database.db'

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS request_logs
        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
         ip_address TEXT, 
         symbol TEXT, 
         timeframe TEXT, 
         created_at DATETIME)
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS fundamentals
        (symbol TEXT PRIMARY KEY,
         fk REAL,
         pddd REAL,
         fd_favok REAL,
         roe REAL,
         last_updated DATETIME)
    ''')
    conn.commit()
    conn.close()

def get_csv_path():
    csv_path = 'shareCodes.csv'
    if not os.path.exists(csv_path):
        parent_dir_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'shareCodes.csv')
        if os.path.exists(parent_dir_path):
            csv_path = parent_dir_path
        else:
            csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'shareCodes.csv')
    return csv_path

is_scraping = False

def scrape_all_fundamentals_task():
    global is_scraping
    if is_scraping:
        print("Scraping already in progress. Skipping.")
        return
    is_scraping = True
    print("Starting background fundamentals scraping...")
    
    csv_path = get_csv_path()
    if not os.path.exists(csv_path):
        print(f"Error: shareCodes.csv not found at {csv_path}")
        is_scraping = False
        return
        
    try:
        df = pd.read_csv(csv_path, header=None)
        raw_symbols = df[0].dropna().astype(str).str.strip().tolist()
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        is_scraping = False
        return

    csv_symbols = [sym if sym.endswith(".IS") else f"{sym}.IS" for sym in raw_symbols if sym]
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # 1. Insert placeholders for any symbols in CSV that are not in DB
    placeholder_time = '1970-01-01 00:00:00'
    for sym in csv_symbols:
        c.execute("INSERT OR IGNORE INTO fundamentals (symbol, last_updated) VALUES (?, ?)", (sym, placeholder_time))
    
    # 2. Delete any symbols in DB that are no longer in CSV
    c.execute("SELECT symbol FROM fundamentals")
    db_symbols = [row[0] for row in c.fetchall()]
    csv_set = set(csv_symbols)
    for sym in db_symbols:
        if sym not in csv_set:
            c.execute("DELETE FROM fundamentals WHERE symbol = ?", (sym,))
            
    conn.commit()
    
    # 3. Select only the symbols that are outdated (older than 24 hours) or haven't been successfully scraped yet
    outdated_time = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("SELECT symbol FROM fundamentals WHERE last_updated < ?", (outdated_time,))
    symbols_to_scrape = [row[0] for row in c.fetchall()]
    conn.close()
    
    total = len(symbols_to_scrape)
    if total == 0:
        print("All fundamentals are up-to-date. No scraping needed.")
        is_scraping = False
        return
        
    print(f"Scraping fundamentals for {total} outdated/unpopulated stocks from yfinance...")
    
    for i, sym in enumerate(symbols_to_scrape):
        try:
            ticker = yf.Ticker(sym)
            info = ticker.info
            
            fk = info.get('trailingPE') or info.get('forwardPE')
            pddd = info.get('priceToBook')
            fd_favok = info.get('enterpriseToEbitda')
            roe_raw = info.get('returnOnEquity')
            roe = roe_raw * 100 if roe_raw is not None else None
            
            fk = round(float(fk), 2) if fk is not None else None
            pddd = round(float(pddd), 2) if pddd is not None else None
            fd_favok = round(float(fd_favok), 2) if fd_favok is not None else None
            roe = round(float(roe), 2) if roe is not None else None
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                UPDATE fundamentals
                SET fk = ?, pddd = ?, fd_favok = ?, roe = ?, last_updated = ?
                WHERE symbol = ?
            """, (fk, pddd, fd_favok, roe, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sym))
            conn.commit()
            conn.close()
            
            if (i + 1) % 10 == 0:
                print(f"Scraped fundamentals progress: {i+1}/{total} completed.")
                
        except Exception as e:
            err_msg = str(e)
            print(f"Error scraping fundamentals for {sym}: {err_msg}")
            
            # If we hit a rate limit, abort immediately to respect the provider
            if "Too Many Requests" in err_msg or "Rate limited" in err_msg or "429" in err_msg:
                print("Rate limit detected! Aborting background scraping task to respect API limits.")
                break
                
            # For other errors (like 404), update timestamp so we don't retry endlessly
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("""
                    UPDATE fundamentals
                    SET last_updated = ?
                    WHERE symbol = ?
                """, (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sym))
                conn.commit()
                conn.close()
            except Exception:
                pass
            
        time.sleep(1.5)
        
    is_scraping = False
    print("Background fundamentals scraping finished.")

def trigger_background_scrape():
    thread = threading.Thread(target=scrape_all_fundamentals_task)
    thread.daemon = True
    thread.start()

def check_and_trigger_update():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM fundamentals")
    count = c.fetchone()[0]
    
    csv_path = get_csv_path()
    csv_len = 0
    raw_symbols = []
    if os.path.exists(csv_path):
        try:
            df = pd.read_csv(csv_path, header=None)
            raw_symbols = df[0].dropna().astype(str).str.strip().tolist()
            csv_len = len(raw_symbols)
        except Exception:
            pass
            
    if count < 500 or count != csv_len:
        print(f"Initializing/Wiping fundamentals table. Current count={count}, CSV count={csv_len}")
        c.execute("DELETE FROM fundamentals")
        if raw_symbols:
            try:
                placeholder_time = '1970-01-01 00:00:00'
                for sym in raw_symbols:
                    if not sym:
                        continue
                    formatted_sym = sym if sym.endswith(".IS") else f"{sym}.IS"
                    c.execute("""
                        INSERT OR REPLACE INTO fundamentals (symbol, fk, pddd, fd_favok, roe, last_updated)
                        VALUES (?, NULL, NULL, NULL, NULL, ?)
                    """, (formatted_sym, placeholder_time))
                conn.commit()
                print(f"Inserted placeholders for {len(raw_symbols)} symbols.")
            except Exception as e:
                print(f"Error seeding database placeholders: {e}")
                
    # Check if there are any unpopulated placeholders (never successfully scraped or retried)
    c.execute("SELECT COUNT(*) FROM fundamentals WHERE last_updated = '1970-01-01 00:00:00'")
    unpopulated_count = c.fetchone()[0]
    
    needs_update = False
    if unpopulated_count > 0:
        needs_update = True
        print(f"Found {unpopulated_count} unpopulated stock placeholders in database.")
    else:
        # If all are populated, check the age of the oldest cache entry
        c.execute("SELECT MIN(last_updated) FROM fundamentals")
        oldest_str = c.fetchone()[0]
        if oldest_str is None:
            needs_update = True
        else:
            try:
                oldest_dt = datetime.strptime(oldest_str, "%Y-%m-%d %H:%M:%S")
                if datetime.now() - oldest_dt > timedelta(hours=24):
                    needs_update = True
            except Exception:
                needs_update = True
    conn.close()
            
    if needs_update:
        print("Database cache is outdated (older than 24h) or unpopulated. Triggering background scrape...")
        trigger_background_scrape()
    else:
        print("Database cache is fresh (less than 24h old). No update required.")

scheduler = BackgroundScheduler()

@app.on_event("startup")
def start_scheduler():
    init_db()
    check_and_trigger_update()
    scheduler.add_job(trigger_background_scrape, 'cron', hour=18, minute=30)
    scheduler.start()
    print("Background scheduler started successfully.")

@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()
    print("Background scheduler stopped.")

def calculate_opportunity_score(fk: float, pddd: float, fd_favok: float, roe: float) -> int:
    score = 0
    # P/E Ratio (F/K) (Max 25 Points)
    if fk is not None:
        if 0 <= fk <= 6:
            score += 25
        elif 6.01 <= fk <= 10:
            score += 15
        elif 10.01 <= fk <= 15:
            score += 5
            
    # P/B Ratio (PD/DD) (Max 25 Points)
    if pddd is not None:
        if 0 <= pddd <= 1.5:
            score += 25
        elif 1.51 <= pddd <= 3:
            score += 15
        elif 3.01 <= pddd <= 5:
            score += 5
            
    # EV/EBITDA (FD/FAVÖK) (Max 25 Points)
    if fd_favok is not None:
        if 0 <= fd_favok <= 5:
            score += 25
        elif 5.01 <= fd_favok <= 8:
            score += 15
        elif 8.01 <= fd_favok <= 12:
            score += 5
            
    # ROE (Return on Equity) (Max 25 Points)
    if roe is not None:
        if roe >= 35:
            score += 25
        elif 20 <= roe < 35:
            score += 15
        elif 10 <= roe < 20:
            score += 5
            
    return score

def get_start_date(period: str, custom_date: str = None) -> str:
    today = datetime.now()
    if period == "1w":
        dt = today - timedelta(weeks=1)
    elif period == "1m":
        dt = today - timedelta(days=30)
    elif period == "3m":
        dt = today - timedelta(days=90)
    elif period == "6m":
        dt = today - timedelta(days=180)
    elif period == "1y":
        dt = today - timedelta(days=365)
    elif period == "custom" and custom_date:
        return custom_date
    else:
        dt = today - timedelta(days=30)
    return dt.strftime("%Y-%m-%d")

def get_ticker_return(symbol: str, start_date_str: str) -> float:
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date_str)
    if df.empty or len(df) < 1:
        raise ValueError(f"No history data returned for ticker {symbol}")
    start_price = df['Close'].iloc[0]
    end_price = df['Close'].iloc[-1]
    pct_return = ((end_price - start_price) / start_price) * 100
    return round(pct_return, 2)

@app.get("/api/screener")
async def run_screener(
    period: str = "1m",
    custom_date: str = None
):
    try:
        start_date_str = get_start_date(period, custom_date)
        
        # Get stock fundamentals from DB
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT symbol, fk, pddd, fd_favok, roe, last_updated FROM fundamentals")
        rows = c.fetchall()
        conn.close()
        
        if not rows:
            return JSONResponse(content={
                "bist100_return": 0.0,
                "results": [],
                "start_date": start_date_str
            })
            
        # Build symbols list and add index symbol
        symbols = [row[0] for row in rows]
        symbols_to_download = list(set(symbols + ["XU100.IS"]))
        
        # Batch download historical prices
        try:
            df_prices = yf.download(symbols_to_download, start=start_date_str, progress=False)
        except Exception as e:
            return JSONResponse(status_code=500, content={"hata": f"Batch download failed: {str(e)}"})
            
        if df_prices.empty or 'Close' not in df_prices:
            return JSONResponse(status_code=500, content={"hata": "Download returned empty price dataframe."})
            
        df_close = df_prices['Close']
        if isinstance(df_close, pd.Series):
            df_close = df_close.to_frame()
            
        # Calculate index return (XU100.IS)
        if "XU100.IS" in df_close.columns:
            bist100_series = df_close["XU100.IS"].dropna()
        else:
            try:
                bist100_series = yf.download("XU100.IS", start=start_date_str, progress=False)['Close'].dropna()
            except Exception:
                bist100_series = pd.Series()
                
        if bist100_series.empty or len(bist100_series) < 1:
            return JSONResponse(status_code=400, content={"hata": f"BIST100 endeks verisi alınamadı ({start_date_str} tarihinden itibaren)."})
            
        bist100_start = bist100_series.iloc[0]
        bist105_end = bist100_series.iloc[-1]
        bist100_return = round(((bist105_end - bist100_start) / bist100_start) * 100, 2)
        
        results = []
        for symbol, fk, pddd, fd_favok, roe, last_updated in rows:
            try:
                if symbol not in df_close.columns:
                    continue
                    
                series = df_close[symbol].dropna()
                if series.empty or len(series) < 1:
                    continue
                    
                start_price = series.iloc[0]
                end_price = series.iloc[-1]
                
                if start_price <= 0:
                    continue
                    
                stock_return = round(((end_price - start_price) / start_price) * 100, 2)
                
                # Filter: ONLY stocks whose returns are below the index return
                if stock_return < bist100_return:
                    score = calculate_opportunity_score(fk, pddd, fd_favok, roe)
                    results.append({
                        "symbol": symbol,
                        "return": stock_return,
                        "fk": fk,
                        "pddd": pddd,
                        "fd_favok": fd_favok,
                        "roe": roe,
                        "score": score,
                        "last_updated": last_updated
                    })
            except Exception as e:
                # Log the issue but do not crash the endpoint
                print(f"Screener: Error calculating return for {symbol}: {str(e)}")
                continue
                
        # Sort from highest score to lowest by default
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return JSONResponse(content={
            "bist100_return": bist100_return,
            "results": results,
            "start_date": start_date_str
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"hata": str(e)})

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

translations = {
    "tr": {
        "symbol": "sembol",
        "timeframe": "zaman_dilimi_periyodu",
        "start_date": "baslangic_tarihi",
        "end_date": "bitis_tarihi",
        "analysis_purpose": "analiz_amaci",
        "analysis_purpose_desc": "Bu veri bir yapay zeka modelinin teknik analiz yapabilmesi için hazırlanmıştır.",
        "candle_series": "mum_serisi",
        "time": "zaman",
        "price_action": "fiyat_hareketi",
        "open": "acilis",
        "high": "en_yuksek",
        "low": "en_dusuk",
        "close": "kapanis",
        "volume": "hacim",
        "indicators": "indikatorler"
    },
    "en": {
        "symbol": "symbol",
        "timeframe": "timeframe",
        "start_date": "start_date",
        "end_date": "end_date",
        "analysis_purpose": "analysis_purpose",
        "analysis_purpose_desc": "This data has been prepared for an artificial intelligence model to perform technical analysis.",
        "candle_series": "candle_series",
        "time": "time",
        "price_action": "price_action",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "volume": "volume",
        "indicators": "indicators"
    }
}

@app.post("/api/generate_json")
async def generate_json(
    request: Request,
    symbol: str = Form(...),
    timeframe: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    indicators: str = Form(...), # Virgülle ayrılmış string (Örn: "EMA9,EMA21,RSI")
    exchange: str = Form(...),
    lang: str = Form("tr")
):
    try:
        # Sembolü temizle ve büyük harf yap
        symbol = symbol.strip().upper()

        # 2. Seçilen borsaya göre sembol sonekini ayarla
        if exchange == "bist":
            if not symbol.endswith(".IS"):
                symbol = f"{symbol}.IS"
        elif exchange == "crypto":
            if not symbol.endswith("-USD"):
                symbol = f"{symbol}-USD"
        elif exchange == "lse":
            if not symbol.endswith(".L"):
                symbol = f"{symbol}.L"
        elif exchange == "xetra":
            if not symbol.endswith(".DE"):
                symbol = f"{symbol}.DE"
        elif exchange == "tse":
            if not symbol.endswith(".T"):
                symbol = f"{symbol}.T"
        elif exchange == "euronext":
            if not symbol.endswith(".PA"):
                symbol = f"{symbol}.PA"
        # "us" durumunda herhangi bir sonek eklemiyoruz

        # 1. İstek Logunu Veritabanına Kaydet (Sembolün nihai halini logluyoruz)
        client_ip = request.client.host
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO request_logs (ip_address, symbol, timeframe, created_at) VALUES (?, ?, ?, ?)",
                  (client_ip, symbol, timeframe, datetime.now()))
        conn.commit()
        conn.close()

        # Bitiş tarihine 1 gün ekliyoruz çünkü yfinance end parametresi hariç (exclusive) çalışır
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d") + pd.Timedelta(days=1)
        end_date_str = end_date_obj.strftime("%Y-%m-%d")

        df = yf.Ticker(symbol).history(start=start_date, end=end_date_str, interval=timeframe)
        
        if df.empty:
            return JSONResponse(status_code=404, content={"hata": "Veri bulunamadı. Lütfen tarih aralığını ve sembolü kontrol edin. (Not: 1 dakikalık veriler sadece son 7 gün için çekilebilir)"})

        # 3. İndikatörleri Hesapla (pandas-ta kullanarak)
        indicator_list = [i.strip().upper() for i in indicators.split(",")]
        
        if "EMA9" in indicator_list:
            df.ta.ema(length=9, append=True)
        if "EMA21" in indicator_list:
            df.ta.ema(length=21, append=True)
        if "SMA50" in indicator_list:
            df.ta.sma(length=50, append=True)
        if "SMA200" in indicator_list:
            df.ta.sma(length=200, append=True)
        if "RSI" in indicator_list:
            df.ta.rsi(length=14, append=True)
        if "MACD" in indicator_list:
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
        if "BBANDS" in indicator_list:
            df.ta.bbands(length=20, std=2, append=True)
        if "STOCH" in indicator_list:
            df.ta.stoch(k=14, d=3, smooth_k=3, append=True)
        if "ATR" in indicator_list:
            df.ta.atr(length=14, append=True)
        if "ADX" in indicator_list:
            df.ta.adx(length=14, append=True)
        if "CCI" in indicator_list:
            df.ta.cci(length=14, append=True)
        if "OBV" in indicator_list:
            df.ta.obv(append=True)

        # Dil seçimine göre kelimeleri al (varsayılan: tr)
        t = translations.get(lang, translations["tr"])

        # 4. Veriyi Hiyerarşik AI Formatına (JSON) Dönüştür
        json_output = {
            t["symbol"]: symbol,
            t["timeframe"]: timeframe,
            t["start_date"]: start_date,
            t["end_date"]: end_date,
            t["analysis_purpose"]: t["analysis_purpose_desc"],
            t["candle_series"]: []
        }

        # Sütunları güvenli şekilde almak için yardımcı fonksiyon
        def get_val(r, col_name):
            if col_name in df.columns:
                v = r[col_name]
                if pd.notna(v):
                    return round(float(v), 2)
            return None

        for index, row in df.iterrows():
            mum_verisi = {
                t["time"]: index.strftime('%Y-%m-%d %H:%M:%S'),
                t["price_action"]: {
                    t["open"]: round(row['Open'], 2),
                    t["high"]: round(row['High'], 2),
                    t["low"]: round(row['Low'], 2),
                    t["close"]: round(row['Close'], 2),
                    t["volume"]: int(row['Volume'])
                },
                t["indicators"]: {}
            }
            
            # Dinamik olarak hesaplanan indikatörleri ekle
            if "EMA9" in indicator_list:
                val = get_val(row, 'EMA_9')
                if val is not None: mum_verisi[t["indicators"]]["EMA_9"] = val
            if "EMA21" in indicator_list:
                val = get_val(row, 'EMA_21')
                if val is not None: mum_verisi[t["indicators"]]["EMA_21"] = val
            if "SMA50" in indicator_list:
                val = get_val(row, 'SMA_50')
                if val is not None: mum_verisi[t["indicators"]]["SMA_50"] = val
            if "SMA200" in indicator_list:
                val = get_val(row, 'SMA_200')
                if val is not None: mum_verisi[t["indicators"]]["SMA_200"] = val
            if "RSI" in indicator_list:
                val = get_val(row, 'RSI_14')
                if val is not None: mum_verisi[t["indicators"]]["RSI_14"] = val
                
            if "MACD" in indicator_list:
                macd = get_val(row, 'MACD_12_26_9')
                macdh = get_val(row, 'MACDh_12_26_9')
                macds = get_val(row, 'MACDs_12_26_9')
                if macd is not None: mum_verisi[t["indicators"]]["MACD"] = macd
                if macdh is not None: mum_verisi[t["indicators"]]["MACD_Histogram"] = macdh
                if macds is not None: mum_verisi[t["indicators"]]["MACD_Signal"] = macds
                
            if "BBANDS" in indicator_list:
                bbl = get_val(row, 'BBL_20_2.0_2.0')
                bbm = get_val(row, 'BBM_20_2.0_2.0')
                bbu = get_val(row, 'BBU_20_2.0_2.0')
                if bbl is not None: mum_verisi[t["indicators"]]["Bollinger_Lower"] = bbl
                if bbm is not None: mum_verisi[t["indicators"]]["Bollinger_Middle"] = bbm
                if bbu is not None: mum_verisi[t["indicators"]]["Bollinger_Upper"] = bbu
                
            if "STOCH" in indicator_list:
                stoch_k = get_val(row, 'STOCHk_14_3_3')
                stoch_d = get_val(row, 'STOCHd_14_3_3')
                if stoch_k is not None: mum_verisi[t["indicators"]]["Stoch_K"] = stoch_k
                if stoch_d is not None: mum_verisi[t["indicators"]]["Stoch_D"] = stoch_d
 
            if "ATR" in indicator_list:
                atr = get_val(row, 'ATRr_14')
                if atr is not None: mum_verisi[t["indicators"]]["ATR"] = atr
 
            if "ADX" in indicator_list:
                adx = get_val(row, 'ADX_14')
                if adx is not None: mum_verisi[t["indicators"]]["ADX"] = adx
 
            if "CCI" in indicator_list:
                cci = get_val(row, 'CCI_14_0.015')
                if cci is not None: mum_verisi[t["indicators"]]["CCI"] = cci
 
            if "OBV" in indicator_list:
                obv = get_val(row, 'OBV')
                if obv is not None: mum_verisi[t["indicators"]]["OBV"] = obv
                
            json_output[t["candle_series"]].append(mum_verisi)
 
        return JSONResponse(content=json_output)

    except Exception as e:
        return JSONResponse(status_code=500, content={"hata": str(e)})