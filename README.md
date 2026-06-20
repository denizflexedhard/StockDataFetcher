# AI Trade Bridge - Yapay Zeka Uyumlu Finansal Veri Dönüştürücü

**AI Trade Bridge**, finansal piyasa verilerini ve teknik indikatörleri, Büyük Dil Modellerinin (LLM - ChatGPT, Gemini, Claude vb.) kolayca anlayabileceği, optimize edilmiş hiyerarşik JSON formatına dönüştüren modern ve hızlı bir web uygulamasıdır.

Uygulama, yapay zekaya teknik analiz yaptırmak isteyen geliştiriciler ve yatırımcılar için kusursuz ve token-tasarruflu veri dosyaları hazırlar.

---

## 🌟 Öne Çıkan Özellikler

- **Çoklu Borsa ve Piyasa Desteği:** 
  - Borsa İstanbul (BIST)
  - ABD Borsaları (NASDAQ / NYSE)
  - Kripto Paralar (USD Bazlı)
  - Londra Borsası (LSE)
  - Frankfurt Borsası (XETRA)
  - Tokyo Borsası (TSE)
  - Paris Borsası (Euronext)
- **Dinamik ve Akıllı Arayüz:** Seçilen borsaya göre otomatik değişen örnek semboller, etiketler ve modern kullanıcı deneyimi.
- **Gelişmiş Teknik İndikatör Hesaplama:** `pandas-ta` kütüphanesi kullanılarak en popüler indikatörler anında hesaplanır ve mum serisine eklenir.
- **İstek Kaydı & Loglama:** SQLite veritabanı sayesinde IP adresi, aratılan sembol ve zaman dilimi loglanır.
- **Token Dostu Hiyerarşik JSON Çıktısı:** LLM'lerin verileri en doğru şekilde anlamlandırması için özel olarak tasarlanmış veri şeması.

---

## 🛠️ Teknoloji Yığını

- **Backend:** Python, FastAPI (Asenkron ve Yüksek Performanslı)
- **Veri Çekme:** `yfinance` (Yahoo Finance API)
- **Teknik Analiz:** `pandas` & `pandas-ta`
- **Veritabanı:** SQLite
- **Frontend:** HTML5, Vanilla JavaScript, Tailwind CSS (CDN)

---

## 📂 Klasör Yapısı

```text
ai_trade_bridge/
│
├── main.py              # FastAPI backend kodumuz
├── requirements.txt     # Python kütüphaneleri
├── ai_database.db       # SQLite veritabanımız (otomatik oluşacak)
│
└── templates/
    └── index.html       # Kullanıcı arayüzümüz
```

---

## 🚀 Kurulum ve Çalıştırma

### 1. Gereksinimler
Sisteminizde **Python 3.8+** sürümünün kurulu olduğundan emin olun.

### 2. Bağımlılıkları Yükleyin
Proje dizinine terminal üzerinden giderek aşağıdaki komutla gerekli kütüphaneleri kurun:

```bash
pip install -r requirements.txt
```

### 3. Uygulamayı Başlatın
Uygulamayı geliştiriçi modunda başlatmak için `ai_trade_bridge` dizininde şu komutu çalıştırın:

```bash
python -m uvicorn main:app --reload
```

Uygulama başarıyla başladıktan sonra tarayıcınızdan **[http://127.0.0.1:8000](http://127.0.0.1:8000)** adresine giderek arayüze erişebilirsiniz.

---

## 📊 Desteklenen Teknik İndikatörler

- **EMA9 / EMA21:** Üstel Hareketli Ortalama (9 ve 21 periyot)
- **SMA50 / SMA200:** Basit Hareketli Ortalama (50 ve 200 periyot)
- **RSI:** Göreceli Güç Endeksi (14 periyot)
- **MACD:** Hareketli Ortalama Yakınsama Iraksama (12, 26, 9)
- **BBANDS:** Bollinger Bantları (20 periyot, 2 standart sapma)
- **STOCH:** Stokastik Osilatör (14, 3, 3)
- **ATR:** Ortalama Gerçek Aralık (14 periyot)
- **ADX:** Ortalama Yönsel Endeks (14 periyot)
- **CCI:** Emtia Kanalı Endeksi (14 periyot)
- **OBV:** Dengedeki Hacim

---

## 📋 Örnek JSON Çıktısı

Uygulamanın ürettiği ve yapay zekaya doğrudan yükleyebileceğiniz JSON dosyasının yapısı aşağıdaki gibidir:

```json
{
  "sembol": "THYAO.IS",
  "zaman_dilimi_periyodu": "1d",
  "baslangic_tarihi": "2026-06-01",
  "bitis_tarihi": "2026-06-15",
  "analiz_amaci": "Bu veri bir yapay zeka modelinin teknik analiz yapabilmesi için hazırlanmıştır.",
  "mum_serisi": [
    {
      "zaman": "2026-06-01 00:00:00",
      "fiyat_hareketi": {
        "acilis": 315.5,
        "en_yuksek": 320.0,
        "en_dusuk": 314.2,
        "kapanis": 318.5,
        "hacim": 12504800
      },
      "indikatorler": {
        "EMA_9": 316.2,
        "RSI_14": 55.4
      }
    }
  ]
}
```

---

## 📝 Lisans

Bu proje eğitim ve kişisel kullanım amacıyla geliştirilmiştir. Verilerin doğruluğu Yahoo Finance API servisinin kalitesine bağlıdır, yatırım tavsiyesi içermez.
