from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import pandas_ta as ta
import sqlite3
from datetime import datetime

app = FastAPI(title="AI Trade Bridge API")

# HTML şablonları için klasör
templates = Jinja2Templates(directory="templates")

# CORS ayarları (Frontend'in API'ye erişebilmesi için)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Veritabanı Kurulumu
def init_db():
    conn = sqlite3.connect('ai_database.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS request_logs
        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
         ip_address TEXT, 
         symbol TEXT, 
         timeframe TEXT, 
         created_at DATETIME)
    ''')
    conn.commit()
    conn.close()

init_db()

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/generate_json")
async def generate_json(
    request: Request,
    symbol: str = Form(...),
    timeframe: str = Form(...),
    start_date: str = Form(...),
    end_date: str = Form(...),
    indicators: str = Form(...) # Virgülle ayrılmış string (Örn: "EMA9,EMA21,RSI")
):
    try:
        # 1. İstek Logunu Veritabanına Kaydet
        client_ip = request.client.host
        conn = sqlite3.connect('ai_database.db')
        c = conn.cursor()
        c.execute("INSERT INTO request_logs (ip_address, symbol, timeframe, created_at) VALUES (?, ?, ?, ?)",
                  (client_ip, symbol, timeframe, datetime.now()))
        conn.commit()
        conn.close()

        # 2. Yahoo Finance'den Veriyi Çek (BİST hisseleri için sonuna .IS eklemeyi unutma)
        if not symbol.endswith(".IS") and not symbol.endswith("USD"):
             symbol = f"{symbol}.IS" # BİST varsayılanı

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

        # 4. Veriyi Hiyerarşik AI Formatına (JSON) Dönüştür
        json_output = {
            "sembol": symbol,
            "zaman_dilimi_periyodu": timeframe,
            "baslangic_tarihi": start_date,
            "bitis_tarihi": end_date,
            "analiz_amaci": "Bu veri bir yapay zeka modelinin teknik analiz yapabilmesi için hazırlanmıştır.",
            "mum_serisi": []
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
                "zaman": index.strftime('%Y-%m-%d %H:%M:%S'),
                "fiyat_hareketi": {
                    "acilis": round(row['Open'], 2),
                    "en_yuksek": round(row['High'], 2),
                    "en_dusuk": round(row['Low'], 2),
                    "kapanis": round(row['Close'], 2),
                    "hacim": int(row['Volume'])
                },
                "indikatorler": {}
            }
            
            # Dinamik olarak hesaplanan indikatörleri ekle
            if "EMA9" in indicator_list:
                val = get_val(row, 'EMA_9')
                if val is not None: mum_verisi["indikatorler"]["EMA_9"] = val
            if "EMA21" in indicator_list:
                val = get_val(row, 'EMA_21')
                if val is not None: mum_verisi["indikatorler"]["EMA_21"] = val
            if "SMA50" in indicator_list:
                val = get_val(row, 'SMA_50')
                if val is not None: mum_verisi["indikatorler"]["SMA_50"] = val
            if "SMA200" in indicator_list:
                val = get_val(row, 'SMA_200')
                if val is not None: mum_verisi["indikatorler"]["SMA_200"] = val
            if "RSI" in indicator_list:
                val = get_val(row, 'RSI_14')
                if val is not None: mum_verisi["indikatorler"]["RSI_14"] = val
                
            if "MACD" in indicator_list:
                macd = get_val(row, 'MACD_12_26_9')
                macdh = get_val(row, 'MACDh_12_26_9')
                macds = get_val(row, 'MACDs_12_26_9')
                if macd is not None: mum_verisi["indikatorler"]["MACD"] = macd
                if macdh is not None: mum_verisi["indikatorler"]["MACD_Histogram"] = macdh
                if macds is not None: mum_verisi["indikatorler"]["MACD_Signal"] = macds
                
            if "BBANDS" in indicator_list:
                bbl = get_val(row, 'BBL_20_2.0_2.0')
                bbm = get_val(row, 'BBM_20_2.0_2.0')
                bbu = get_val(row, 'BBU_20_2.0_2.0')
                if bbl is not None: mum_verisi["indikatorler"]["Bollinger_Lower"] = bbl
                if bbm is not None: mum_verisi["indikatorler"]["Bollinger_Middle"] = bbm
                if bbu is not None: mum_verisi["indikatorler"]["Bollinger_Upper"] = bbu
                
            if "STOCH" in indicator_list:
                stoch_k = get_val(row, 'STOCHk_14_3_3')
                stoch_d = get_val(row, 'STOCHd_14_3_3')
                if stoch_k is not None: mum_verisi["indikatorler"]["Stoch_K"] = stoch_k
                if stoch_d is not None: mum_verisi["indikatorler"]["Stoch_D"] = stoch_d

            if "ATR" in indicator_list:
                atr = get_val(row, 'ATRr_14')
                if atr is not None: mum_verisi["indikatorler"]["ATR"] = atr

            if "ADX" in indicator_list:
                adx = get_val(row, 'ADX_14')
                if adx is not None: mum_verisi["indikatorler"]["ADX"] = adx

            if "CCI" in indicator_list:
                cci = get_val(row, 'CCI_14_0.015')
                if cci is not None: mum_verisi["indikatorler"]["CCI"] = cci

            if "OBV" in indicator_list:
                obv = get_val(row, 'OBV')
                if obv is not None: mum_verisi["indikatorler"]["OBV"] = obv
                
            json_output["mum_serisi"].append(mum_verisi)

        return JSONResponse(content=json_output)

    except Exception as e:
        return JSONResponse(status_code=500, content={"hata": str(e)})