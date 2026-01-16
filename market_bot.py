import os
import yfinance as yf
import google.generativeai as genai
import feedparser
import datetime
import requests
import time
import pandas as pd
import re
from bs4 import BeautifulSoup

# --- 設定 Gemini ---
def configure_genai(api_key):
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        print(f"⚠️ Gemini 設定失敗: {e}")

# --- 抓新聞 (含摘要與防擋) ---
def get_financial_news():
    rss_sources = [
        "https://news.google.com/rss/topics/CAAqJggBCiCPASowCAqXAg8KCOgDPQkKBAgCGAISBAgBEgISBAgQEgIIABIECAESBAgBEg?hl=en-US&gl=US&ceid=US:en",
        "https://finance.yahoo.com/news/rssindex"
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }
    try:
        for url in rss_sources:
            print(f"📰 正在嘗試抓取新聞來源: {url} ...")
            response = requests.get(url, headers=headers, timeout=10)
            feed = feedparser.parse(response.content)
            if feed.entries:
                print(f"✅ 成功抓到新聞！(共 {len(feed.entries)} 則)")
                news_items = []
                for entry in feed.entries[:8]:
                    title = entry.title
                    raw_summary = getattr(entry, 'summary', '') or getattr(entry, 'description', '')
                    clean_summary = ""
                    if raw_summary:
                        soup = BeautifulSoup(raw_summary, "html.parser")
                        clean_summary = soup.get_text(separator=' ', strip=True)
                        if len(clean_summary) > 200: 
                            clean_summary = clean_summary[:200] + "..."
                    item_text = f"Title: {title}\nSummary: {clean_summary}\n"
                    news_items.append(item_text)
                return "\n-----------------\n".join(news_items)
        return "⚠️ 今日無重大頭條 (所有新聞來源皆無回應)"
    except Exception as e:
        print(f"❌ 新聞抓取系統故障: {e}")
        return "新聞抓取失敗"

# --- 抓 AAII 完整數據 (日期嚴格過濾版) ---
def get_aaii_sentiment():
    print("🕵️ 抓取 AAII 數據 (日期嚴格修復)...")
    url = "https://www.aaii.com/sentimentsurvey"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Referer": "https://www.google.com/"
    }
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200: return None, None

        soup = BeautifulSoup(r.text, 'html.parser')
        for script in soup(["script", "style"]): script.extract()
        clean_text = soup.get_text(separator=' ', strip=True)
        
        months = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*"
        date_pattern = rf"(\d{{1,2}}/\d{{1,2}}/\d{{2,4}}|{months}\s+\d{{1,2}},?\s+\d{{4}})"
        date_match = re.search(date_pattern, clean_text, re.IGNORECASE)
        
        bull_match = re.search(r'Bullish.*?(\d{1,2}\.\d)%', clean_text, re.IGNORECASE)
        neut_match = re.search(r'Neutral.*?(\d{1,2}\.\d)%', clean_text, re.IGNORECASE)
        bear_match = re.search(r'Bearish.*?(\d{1,2}\.\d)%', clean_text, re.IGNORECASE)

        if bull_match and neut_match and bear_match:
            bull = float(bull_match.group(1))
            neut = float(neut_match.group(1))
            bear = float(bear_match.group(1))
            
            if 99.0 <= (bull + neut + bear) <= 101.0:
                if date_match:
                    raw_date = date_match.group(1)
                    try:
                        dt = pd.to_datetime(raw_date)
                        short_date = dt.strftime("%m/%d")
                    except:
                        short_date = raw_date
                else:
                    short_date = datetime.date.today().strftime("%m/%d")

                full_str = f"Bull:{bull}% Neut:{neut}% Bear:{bear}% ({short_date})"
                print(f"✅ AAII 成功: {full_str}")
                return full_str, "真實數據"
        return None, None
    except Exception as e:
        print(f"⚠️ AAII 錯誤: {e}")
        return None, None

# --- 抓 CNN 恐懼貪婪指數 ---
def get_cnn_fear_greed():
    print("🕵️ 抓取 CNN 指數...")
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Referer": "https://www.cnn.com/"
        }
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            score = data['fear_and_greed']['score']
            return score
        return None
    except: return None

# --- 抓市場數據 ---
def get_market_data():
    tickers = ['^VIX', 'SPY', 'RSP', 'QQQ', 'IWM', '^TNX', '^IRX', 'SOXX'] 
    print("📥 下載市場數據...")
    try:
        df = yf.download(tickers, period='40d', progress=False, actions=False)['Close']
        if df.empty: raise Exception("數據表為空")

        df = df.ffill()
        latest = df.iloc[-1]
        
        if pd.isna(latest['SPY']):
            latest = df.iloc[-2]
            df_calc = df.iloc[:-1]
        else:
            df_calc = df
            
        aaii_str, aaii_src = get_aaii_sentiment()
        cnn_score = get_cnn_fear_greed()
        
        delta = df_calc['SPY'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        ma_20 = df_calc['SPY'].rolling(window=20).mean().iloc[-1]
        bias = ((latest['SPY'] - ma_20) / ma_20) * 100
        
        if aaii_str is not None:
            aaii_display = aaii_str
            aaii_source = "真實數據"
        else:
            aaii_display = f"RSI:{current_rsi:.1f} (模擬數值)"
            aaii_source = "RSI替代"

        if cnn_score is not None:
            cnn_display = f"{cnn_score:.0f}"
            cnn_src = "真實數據"
        else:
            simulated_score = max(0, min(100, 50 + (bias * 10)))
            cnn_display = f"{simulated_score:.1f} (乖離推算)"
            cnn_src = "乖離率替代"

        prev = df_calc.iloc[-2]
        def calc_change(curr, prev):
            if pd.isna(prev) or prev == 0: return 0.0
            return ((curr - prev) / prev) * 100

        breadth_ratio = latest['RSP'] / latest['SPY'] if latest['SPY'] else 0
        data_date = latest.name.date()

        return {
            'date': data_date,
            'vix': latest['^VIX'],
            'tnx': latest['^TNX'],
            'fed_rate': latest['^IRX'],
            'spy': latest['SPY'],
            'spy_chg': calc_change(latest['SPY'], prev['SPY']),
            'qqq_chg': calc_change(latest['QQQ'], prev['QQQ']),
            'soxx_chg': calc_change(latest['SOXX'], prev['SOXX']),
            'breadth': breadth_ratio,
            'aaii_display': aaii_display,
            'aaii_src': aaii_source,
            'cnn_display': cnn_display,
            'cnn_src': cnn_src
        }
    except Exception as e:
        print(f"❌ 數據錯誤: {e}")
        return None

# --- 生成報告 ---
def generate_ai_report(data, news_text):
    print("🔍 查詢模型...")
    all_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                all_models.append(m.name)
    except: return "❌ Google API 連線失敗"
    
    if not all_models: return "❌ 無可用模型"

    def priority_sort(name):
        name = name.lower()
        if 'flash' in name and '1.5' in name: return 0 
        if 'flash' in name: return 1
        if 'pro' in name and '1.5' in name: return 2
        return 3
    all_models.sort(key=priority_sort)
    
    prompt = f"""
    你是一位華爾街量化分析師。請根據以下數據，製作一份「繁體中文」日報。

    【今日關鍵數據】
    - 日期: {data['date']}
    - AAII 散戶情緒: {data['aaii_display']} (來源: {data['aaii_src']})
    - CNN 恐懼貪婪: {data['cnn_display']} (來源: {data['cnn_src']})
    - VIX 恐慌指數: {data['vix']:.2f}
    - 市場廣度 (RSP/SPY): {data['breadth']:.4f}
    - Fed Rate: {data['fed_rate']:.2f}%

    【新聞輸入 (含摘要)】
    {news_text}

    【報告輸出格式】
    請嚴格遵守以下 Markdown 格式：

    # 🦅 {data['date']} 全方位投資策略分析

    ## 1. 最新市場體檢報告
    (請建立 Markdown Code Block 表格，**AAII 數值較長，請確保表格寬度足夠**)
    ```text
    指標            數值                               歷史位階/狀態       解讀
    --------------------------------------------------------------------------------------
    AAII 散戶情緒   {data['aaii_display']}   (請判斷)          (解讀散戶多空配置)
    VIX 恐慌指數    {data['vix']:.2f}                       (請判斷)          (解讀避險需求)
    CNN 恐懼貪婪    {data['cnn_display']}                       (請判斷)          (解讀市場心理)
    市場廣度        {data['breadth']:.3f}                       (請判斷)          (解讀漲勢健康度)
    Fed Rate (利率) {data['fed_rate']:.2f}%                       (請判斷)          (解讀資金成本)
    ```

    ## 2. 📰 當日重大財經新聞
    (請歸納 3 點，並包含具體摘要)
    * **[新聞標題]**: 摘要內容...
    * **[新聞標題]**: 摘要內容...
    * **[新聞標題]**: 摘要內容...

    ## 3. 🚦 綜合投資策略：(請填入 🟢/🟡/🔴) 燈
    (綜合指標給出燈號)

    **核心觀點**: (一句話總結)

    **操作建議**:
    1.  **資金控管**: ...
    2.  **關注機會**: ...
    3.  **避險策略**: ...

    **結語**: (一句簡短總結)
    """

    last_error = ""
    for model_name in all_models:
        try:
            print(f"🤖 嘗試模型: {model_name} ...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            return f"{response.text}\n\n_(Generated by {model_name})_"
        except Exception as e:
            last_error = str(e)
            time.sleep(1)
            continue
    return f"❌ 所有模型嘗試失敗。錯誤: {last_error}"

# --- 主程式 (支援多群組廣播) ---
if __name__ == "__main__":
    TG_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    CHAT_ID_ENV = os.environ.get('CHAT_ID') # 取得原始字串
    API_KEY = os.environ.get('GEMINI_API_KEY')
    
    if TG_TOKEN and CHAT_ID_ENV and API_KEY:
        try:
            # 1. 解析群組 ID (支援逗號分隔)
            # 例如: "-100123,-100456" -> ['-100123', '-100456']
            chat_ids = [cid.strip() for cid in CHAT_ID_ENV.split(',') if cid.strip()]
            print(f"📢 準備發送報告給 {len(chat_ids)} 個群組: {chat_ids}")

            configure_genai(API_KEY)
            m_data = get_market_data()
            
            if m_data:
                news = get_financial_news()
                # 報告只生成一次，不用重複浪費 AI 額度
                report = generate_ai_report(m_data, news)
                
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                
                # 2. 迴圈發送給所有群組
                for cid in chat_ids:
                    print(f"📤 正在發送給群組 {cid} ...")
                    payload = {'chat_id': cid, 'text': report, 'parse_mode': 'Markdown'}
                    
                    response = requests.post(url, data=payload)
                    
                    # 失敗自動降級機制
                    if response.status_code != 200:
                        print(f"⚠️ 群組 {cid} Markdown 發送失敗 ({response.text})，嘗試純文字...")
                        payload['parse_mode'] = ''
                        requests.post(url, data=payload)
                    else:
                        print(f"✅ 群組 {cid} 發送成功")
                        
                    time.sleep(1) # 休息一下，避免被 Telegram 視為垃圾訊息
                    
            else:
                print("⚠️ 數據抓取為空")
        except Exception as e:
            print(f"❌ 執行錯誤: {e}")
    else:
        print("⚠️ 缺少環境變數")
