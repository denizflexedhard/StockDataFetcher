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
        conn = sqlite3.connect('ai_database.db')
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