# **AI Trade Bridge \- Proje Mimari ve Kurulum Rehberi**

Bu belge, finansal grafikleri Büyük Dil Modellerinin (LLM) anlayabileceği hiyerarşik JSON formatına dönüştüren "AI Trade Bridge" projesinin ilk MVP (Minimum Viable Product \- Çalışan En Basit Ürün) sürümünün kurulumunu içerir. Şimdilik üyelik sistemi yoktur, temel işlev "Veriyi Çek \-\> İşle \-\> JSON İndir" şeklindedir.

## **1\. Mimari ve Teknoloji Yığını**

* **Backend:** FastAPI (Python) \- Çok hızlıdır, asenkron çalışır ve veri işleme kütüphaneleriyle tam uyumludur.  
* **Veri İşleme:** yfinance (Geçmiş piyasa verilerini çekmek için) ve pandas-ta (Teknik indikatörleri hesaplamak için).  
* **Frontend:** HTML5, Vanilla JavaScript ve Tailwind CSS (CDN üzerinden, tasarımın şık durması için).  
* **Veritabanı:** SQLite (Şimdilik üyelik yok ama ileride günlük limitleri belirleyebilmek için kimin hangi hisseyi ne zaman arattığını loglamak (kaydetmek) iyi bir pratiktir).

### **Klasör Yapısı**

Proje klasörünü şu şekilde oluşturmalısın:

ai\_trade\_bridge/  
│  
├── main.py              \# FastAPI backend kodumuz  
├── requirements.txt     \# Python kütüphaneleri  
├── ai\_database.db       \# SQLite veritabanımız (otomatik oluşacak)  
└── templates/  
    └── index.html       \# Kullanıcı arayüzümüz

## **2\. Veritabanı Tasarımı (SQLite)**

İleride üyelik sistemi geldiğinde kullanıcılara "Günde 5 kez dönüştürme hakkı" verebilmek için şimdiden bir **Log (Kayıt)** tablosu tasarlıyoruz.

**Tablo Adı:** request\_logs

* id (INTEGER, Primary Key, Auto Increment)  
* ip\_address (TEXT) \- Kullanıcının IP adresi (Geçici limit koymak için)  
* symbol (TEXT) \- Aratılan hisse (Örn: AKBNK.IS)  
* timeframe (TEXT) \- Seçilen periyot (Örn: 5m)  
* created\_at (DATETIME) \- İşlem zamanı

*(Bu tabloyu main.py çalıştığında otomatik olarak oluşturacak şekilde backend koduna ekledim).*

## **3\. Backend (Python / FastAPI) Kurulumu**

Öncelikle terminalini (CMD/PowerShell) açıp proje klasörüne git ve gerekli kütüphaneleri yükle:

pip install fastapi uvicorn yfinance pandas pandas-ta jinja2

Daha sonra **main.py** dosyasını oluştur ve içine şu kodları yapıştır:

from fastapi import FastAPI, Request, Form  
from fastapi.responses import HTMLResponse, JSONResponse  
from fastapi.templating import Jinja2Templates  
from fastapi.middleware.cors import CORSMiddleware  
import yfinance as yf  
import pandas as pd  
import pandas\_ta as ta  
import sqlite3  
from datetime import datetime

app \= FastAPI(title="AI Trade Bridge API")

\# HTML şablonları için klasör  
templates \= Jinja2Templates(directory="templates")

\# CORS ayarları (Frontend'in API'ye erişebilmesi için)  
app.add\_middleware(  
    CORSMiddleware,  
    allow\_origins=\["\*"\],  
    allow\_methods=\["\*"\],  
    allow\_headers=\["\*"\],  
)

\# Veritabanı Kurulumu  
def init\_db():  
    conn \= sqlite3.connect('ai\_database.db')  
    c \= conn.cursor()  
    c.execute('''  
        CREATE TABLE IF NOT EXISTS request\_logs  
        (id INTEGER PRIMARY KEY AUTOINCREMENT,   
         ip\_address TEXT,   
         symbol TEXT,   
         timeframe TEXT,   
         created\_at DATETIME)  
    ''')  
    conn.commit()  
    conn.close()

init\_db()

@app.get("/", response\_class=HTMLResponse)  
async def read\_root(request: Request):  
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/generate\_json")  
async def generate\_json(  
    request: Request,  
    symbol: str \= Form(...),  
    timeframe: str \= Form(...),  
    period: str \= Form(...),  
    indicators: str \= Form(...) \# Virgülle ayrılmış string (Örn: "EMA9,EMA21,RSI")  
):  
    try:  
        \# 1\. İstek Logunu Veritabanına Kaydet  
        client\_ip \= request.client.host  
        conn \= sqlite3.connect('ai\_database.db')  
        c \= conn.cursor()  
        c.execute("INSERT INTO request\_logs (ip\_address, symbol, timeframe, created\_at) VALUES (?, ?, ?, ?)",  
                  (client\_ip, symbol, timeframe, datetime.now()))  
        conn.commit()  
        conn.close()

        \# 2\. Yahoo Finance'den Veriyi Çek (BİST hisseleri için sonuna .IS eklemeyi unutma)  
        if not symbol.endswith(".IS") and not symbol.endswith("USD"):  
             symbol \= f"{symbol}.IS" \# BİST varsayılanı

        df \= yf.Ticker(symbol).history(period=period, interval=timeframe)  
          
        if df.empty:  
            return JSONResponse(status\_code=404, content={"hata": "Veri bulunamadı. Lütfen sembolü kontrol edin."})

        \# 3\. İndikatörleri Hesapla (pandas-ta kullanarak)  
        indicator\_list \= \[i.strip().upper() for i in indicators.split(",")\]  
          
        if "EMA9" in indicator\_list:  
            df.ta.ema(length=9, append=True)  
        if "EMA21" in indicator\_list:  
            df.ta.ema(length=21, append=True)  
        if "RSI" in indicator\_list:  
            df.ta.rsi(length=14, append=True)

        \# NaN değerleri temizle (indikatör hesaplanamayan ilk mumlar)  
        df.dropna(inplace=True)

        \# 4\. Veriyi Hiyerarşik AI Formatına (JSON) Dönüştür  
        json\_output \= {  
            "sembol": symbol,  
            "zaman\_dilimi\_periyodu": timeframe,  
            "analiz\_amaci": "Bu veri bir yapay zeka modelinin teknik analiz yapabilmesi için hazırlanmıştır.",  
            "mum\_serisi": \[\]  
        }

        for index, row in df.iterrows():  
            mum\_verisi \= {  
                "zaman": index.strftime('%Y-%m-%d %H:%M:%S'),  
                "fiyat\_hareketi": {  
                    "acilis": round(row\['Open'\], 2),  
                    "en\_yuksek": round(row\['High'\], 2),  
                    "en\_dusuk": round(row\['Low'\], 2),  
                    "kapanis": round(row\['Close'\], 2),  
                    "hacim": int(row\['Volume'\])  
                },  
                "indikatorler": {}  
            }  
              
            \# Dinamik olarak hesaplanan indikatörleri ekle  
            if "EMA9" in indicator\_list and 'EMA\_9' in df.columns:  
                mum\_verisi\["indikatorler"\]\["EMA\_9"\] \= round(row\['EMA\_9'\], 2\)  
            if "EMA21" in indicator\_list and 'EMA\_21' in df.columns:  
                mum\_verisi\["indikatorler"\]\["EMA\_21"\] \= round(row\['EMA\_21'\], 2\)  
            if "RSI" in indicator\_list and 'RSI\_14' in df.columns:  
                mum\_verisi\["indikatorler"\]\["RSI\_14"\] \= round(row\['RSI\_14'\], 2\)  
                  
            json\_output\["mum\_serisi"\].append(mum\_verisi)

        return JSONResponse(content=json\_output)

    except Exception as e:  
        return JSONResponse(status\_code=500, content={"hata": str(e)})

## **4\. Frontend (HTML/JS) Arayüzü**

templates klasörünün içine **index.html** dosyasını oluştur ve aşağıdaki kodu yapıştır. Bu arayüz, Bootstrap yerine Tailwind kullanarak şık, modern ve mobil uyumlu bir tasarım sunar.

\<\!DOCTYPE html\>  
\<html lang="tr"\>  
\<head\>  
    \<meta charset="UTF-8"\>  
    \<meta name="viewport" content="width=device-width, initial-scale=1.0"\>  
    \<title\>AI Trade Bridge | Finansal Veri Dönüştürücü\</title\>  
    \<script src="\[https://cdn.tailwindcss.com\](https://cdn.tailwindcss.com)"\>\</script\>  
\</head\>  
\<body class="bg-gray-900 text-white font-sans min-h-screen flex items-center justify-center"\>

    \<div class="bg-gray-800 p-8 rounded-xl shadow-2xl w-full max-w-lg border border-gray-700"\>  
        \<h1 class="text-3xl font-bold text-center text-blue-400 mb-2"\>AI Trade Bridge\</h1\>  
        \<p class="text-center text-gray-400 mb-8 text-sm"\>Yapay Zeka (ChatGPT/Gemini) için kusursuz finansal JSON dosyaları oluşturun.\</p\>

        \<form id="dataForm" class="space-y-5"\>  
            \<\!-- Sembol \--\>  
            \<div\>  
                \<label class="block text-sm font-medium text-gray-300"\>Hisse Sembolü (Örn: AKBNK, THYAO)\</label\>  
                \<input type="text" id="symbol" name="symbol" required placeholder="AKBNK"  
                    class="mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md py-2 px-3 text-white focus:outline-none focus:ring-2 focus:ring-blue-500 uppercase"\>  
            \</div\>

            \<div class="flex space-x-4"\>  
                \<\!-- Zaman Dilimi \--\>  
                \<div class="w-1/2"\>  
                    \<label class="block text-sm font-medium text-gray-300"\>Mum Periyodu\</label\>  
                    \<select id="timeframe" name="timeframe" class="mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md py-2 px-3 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"\>  
                        \<option value="1m"\>1 Dakika\</option\>  
                        \<option value="5m" selected\>5 Dakika\</option\>  
                        \<option value="15m"\>15 Dakika\</option\>  
                        \<option value="1h"\>1 Saat\</option\>  
                        \<option value="1d"\>1 Gün\</option\>  
                    \</select\>  
                \</div\>

                \<\!-- Ne Kadarlık Veri \--\>  
                \<div class="w-1/2"\>  
                    \<label class="block text-sm font-medium text-gray-300"\>Veri Derinliği\</label\>  
                    \<select id="period" name="period" class="mt-1 block w-full bg-gray-700 border border-gray-600 rounded-md py-2 px-3 text-white focus:outline-none focus:ring-2 focus:ring-blue-500"\>  
                        \<option value="1d"\>Son 1 Gün\</option\>  
                        \<option value="5d" selected\>Son 5 Gün\</option\>  
                        \<option value="1mo"\>Son 1 Ay\</option\>  
                    \</select\>  
                \</div\>  
            \</div\>

            \<\!-- İndikatörler \--\>  
            \<div\>  
                \<label class="block text-sm font-medium text-gray-300 mb-2"\>Eklenecek İndikatörler\</label\>  
                \<div class="flex items-center space-x-4 text-sm"\>  
                    \<label class="inline-flex items-center cursor-pointer"\>  
                        \<input type="checkbox" value="EMA9" class="indicator-checkbox form-checkbox h-4 w-4 text-blue-500 bg-gray-700 border-gray-600 rounded" checked\>  
                        \<span class="ml-2"\>EMA 9\</span\>  
                    \</label\>  
                    \<label class="inline-flex items-center cursor-pointer"\>  
                        \<input type="checkbox" value="EMA21" class="indicator-checkbox form-checkbox h-4 w-4 text-blue-500 bg-gray-700 border-gray-600 rounded" checked\>  
                        \<span class="ml-2"\>EMA 21\</span\>  
                    \</label\>  
                    \<label class="inline-flex items-center cursor-pointer"\>  
                        \<input type="checkbox" value="RSI" class="indicator-checkbox form-checkbox h-4 w-4 text-blue-500 bg-gray-700 border-gray-600 rounded"\>  
                        \<span class="ml-2"\>RSI (14)\</span\>  
                    \</label\>  
                \</div\>  
            \</div\>

            \<\!-- Buton \--\>  
            \<button type="submit" id="submitBtn" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 px-4 rounded-md transition duration-200 shadow-lg mt-4"\>  
                JSON Dosyasını Hazırla ve İndir  
            \</button\>  
        \</form\>

        \<div id="statusMsg" class="mt-4 text-center text-sm hidden"\>\</div\>  
    \</div\>

    \<script\>  
        document.getElementById('dataForm').addEventListener('submit', async (e) \=\> {  
            e.preventDefault();  
              
            const btn \= document.getElementById('submitBtn');  
            const statusMsg \= document.getElementById('statusMsg');  
              
            // UI Güncelleme (Yükleniyor)  
            btn.disabled \= true;  
            btn.innerText \= "Veriler Çekiliyor ve Hesaplanıyor...";  
            btn.classList.add("opacity-70");  
            statusMsg.classList.add("hidden");

            // Seçili indikatörleri virgülle ayrılmış string yapma  
            const selectedIndicators \= Array.from(document.querySelectorAll('.indicator-checkbox:checked'))  
                                            .map(cb \=\> cb.value)  
                                            .join(',');

            const formData \= new FormData();  
            formData.append('symbol', document.getElementById('symbol').value);  
            formData.append('timeframe', document.getElementById('timeframe').value);  
            formData.append('period', document.getElementById('period').value);  
            formData.append('indicators', selectedIndicators);

            try {  
                const response \= await fetch('/api/generate\_json', {  
                    method: 'POST',  
                    body: formData  
                });

                const data \= await response.json();

                if (response.ok) {  
                    // Blob oluştur ve dosyayı indir  
                    const jsonString \= JSON.stringify(data, null, 2);  
                    const blob \= new Blob(\[jsonString\], { type: "application/json" });  
                    const url \= URL.createObjectURL(blob);  
                      
                    const a \= document.createElement('a');  
                    a.href \= url;  
                    a.download \= \`AI\_TradeData\_${document.getElementById('symbol').value}\_${document.getElementById('timeframe').value}.json\`;  
                    document.body.appendChild(a);  
                    a.click();  
                    document.body.removeChild(a);  
                    URL.revokeObjectURL(url);

                    statusMsg.innerText \= "✅ Başarılı\! Dosyanız indirildi. Artık yapay zekaya yükleyebilirsiniz.";  
                    statusMsg.className \= "mt-4 text-center text-sm text-green-400 block";  
                } else {  
                    statusMsg.innerText \= "❌ Hata: " \+ (data.hata || "Bilinmeyen bir hata oluştu.");  
                    statusMsg.className \= "mt-4 text-center text-sm text-red-400 block";  
                }  
            } catch (error) {  
                statusMsg.innerText \= "❌ Sunucu bağlantı hatası.";  
                statusMsg.className \= "mt-4 text-center text-sm text-red-400 block";  
            } finally {  
                // UI Sıfırlama  
                btn.disabled \= false;  
                btn.innerText \= "JSON Dosyasını Hazırla ve İndir";  
                btn.classList.remove("opacity-70");  
            }  
        });  
    \</script\>  
\</body\>  
\</html\>

## **5\. Uygulamayı Çalıştırma**

Terminalinde proje dizinindeyken şu komutu çalıştır:

uvicorn main:app \--reload

* Tarayıcını aç ve **http://127.0.0.1:8000** adresine git.  
* Karşına hazırladığımız arayüz çıkacak.  
* AKBNK yaz, 5 Dakika seç, indikatörlerini işaretle ve butona bas.  
* Saniyeler içinde, yapay zekanın anlayacağı kusursuz JSON dosyası bilgisayarına inmiş olacak\!