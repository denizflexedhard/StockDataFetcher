import os
import sys
import time
import sqlite3
from datetime import datetime, timedelta
import pandas as pd
import yfinance as yf

# Set up paths relative to this script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ai_trade_bridge", "ai_database.db")
CSV_PATH = os.path.join(BASE_DIR, "shareCodes.csv")

def clean_float(val):
    if val is None:
        return None
    try:
        fval = float(val)
        import math
        if math.isinf(fval) or math.isnan(fval):
            return None
        return fval
    except (ValueError, TypeError):
        return None

def main():
    force = "--force" in sys.argv or "-f" in sys.argv
    
    print("--- Stock Fundamentals Local Updater ---")
    print(f"Database Path: {DB_PATH}")
    print(f"CSV Path:      {CSV_PATH}")
    if force:
        print("Mode:          FORCE UPDATE (all stocks will be re-scraped)")
    else:
        print("Mode:          INCREMENTAL UPDATE (only outdated/missing stocks)")
    print("----------------------------------------")

    # Ensure DB directory exists
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    # Connect to DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Ensure fundamentals table exists
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

    # Load symbols from CSV
    if not os.path.exists(CSV_PATH):
        print(f"Error: shareCodes.csv not found at {CSV_PATH}")
        return
        
    try:
        df = pd.read_csv(CSV_PATH, header=None)
        raw_symbols = df[0].dropna().astype(str).str.strip().tolist()
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return
        
    csv_symbols = [sym if sym.endswith(".IS") else f"{sym}.IS" for sym in raw_symbols if sym]
    csv_len = len(csv_symbols)
    
    # Sync database rows with CSV list (insert missing, delete old ones)
    placeholder_time = '1970-01-01 00:00:00'
    for sym in csv_symbols:
        c.execute("INSERT OR IGNORE INTO fundamentals (symbol, last_updated) VALUES (?, ?)", (sym, placeholder_time))
    
    c.execute("SELECT symbol FROM fundamentals")
    db_symbols = [row[0] for row in c.fetchall()]
    csv_set = set(csv_symbols)
    for sym in db_symbols:
        if sym not in csv_set:
            c.execute("DELETE FROM fundamentals WHERE symbol = ?", (sym,))
    conn.commit()

    # If force, set everything as outdated
    if force:
        c.execute("UPDATE fundamentals SET last_updated = ?", (placeholder_time,))
        conn.commit()

    # Query targets to scrape (older than 24 hours or unpopulated)
    outdated_time = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    c.execute("SELECT symbol FROM fundamentals WHERE last_updated < ? OR last_updated = ?", (outdated_time, placeholder_time))
    symbols_to_scrape = [row[0] for row in c.fetchall()]
    conn.close()
    
    total = len(symbols_to_scrape)
    if total == 0:
        print("\nAll fundamentals are up-to-date! No scraping required.")
        print("To force-update all data, run: python seed_database.py --force")
        return

    print(f"\nFound {total} symbols that need scraping.")
    print("Scraping will begin. Press CTRL+C to pause/abort at any time.")
    print("----------------------------------------")
    
    for i, sym in enumerate(symbols_to_scrape):
        try:
            ticker = yf.Ticker(sym)
            info = ticker.info
            
            fk = info.get('trailingPE') or info.get('forwardPE')
            pddd = info.get('priceToBook')
            fd_favok = info.get('enterpriseToEbitda')
            roe_raw = info.get('returnOnEquity')
            roe = roe_raw * 100 if roe_raw is not None else None
            
            fk = clean_float(fk)
            pddd = clean_float(pddd)
            fd_favok = clean_float(fd_favok)
            roe = clean_float(roe)
            
            if fk is not None: fk = round(fk, 2)
            if pddd is not None: pddd = round(pddd, 2)
            if fd_favok is not None: fd_favok = round(fd_favok, 2)
            if roe is not None: roe = round(roe, 2)
            
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute("""
                UPDATE fundamentals
                SET fk = ?, pddd = ?, fd_favok = ?, roe = ?, last_updated = ?
                WHERE symbol = ?
            """, (fk, pddd, fd_favok, roe, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sym))
            conn.commit()
            conn.close()
            
            print(f"[{i+1}/{total}] Scraped {sym:9} -> PE: {str(fk):6} | PB: {str(pddd):6} | EV/EBITDA: {str(fd_favok):6} | ROE: {str(roe):6}%")
            
        except KeyboardInterrupt:
            print("\nUpdating paused by user. Progress saved.")
            break
        except Exception as e:
            err_msg = str(e)
            print(f"[{i+1}/{total}] Error scraping {sym}: {err_msg}")
            
            if "Too Many Requests" in err_msg or "Rate limited" in err_msg or "429" in err_msg:
                print("\nRate limit detected! Aborting scraping to prevent IP ban. Please try again later.")
                break
                
            # For general failures, set last_updated so we skip retrying it on this run
            try:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.execute("UPDATE fundamentals SET last_updated = ? WHERE symbol = ?", 
                          (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), sym))
                conn.commit()
                conn.close()
            except Exception:
                pass
                
        # Sleep to avoid rate limits (0.4s is safe for home IPs)
        time.sleep(0.4)
        
    print("\n--- Seeding Process Finished ---")

if __name__ == "__main__":
    main()
