import os
import yfinance as yf
import google.generativeai as genai
import feedparser
import datetime
import requests
import time
import pandas as pd
import re
from bs4 import BeautifulSoup  # 新增：用來清洗新聞摘要裡的 HTML 標籤

# --- 設定 Gemini ---
def configure_genai(api_key):
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        print(f"⚠️ Gemini 設定失敗: {e}")

# --- 抓新聞 (升級版：含摘要與防擋) ---
def get_financial_news():
    # 來源清單：優先抓 Google News，失敗換 Yahoo
    rss_sources = [
        "https://news.google.com/rss/topics/CAAqJggBCiCPASowCAqXAg8KCOgDPQkKBAgCGAISBAgBEgISBAgQEgIIABIECAESBAgBEg?hl=en-US&gl=US&ceid=US:en",
        "https://finance.yahoo.com/news/rssindex"
    ]
    
    # 偽裝成瀏覽器
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }

    try:
        for url in rss_sources:
            print(f"📰 正在嘗試抓取新聞來源: {url} ...")
            response = requests.get(url, headers=headers, timeout=10)
            
            # 使用 feedparser 解析內容
            feed = feedparser.parse(response.content)
            
            if feed.entries:
                print(f"✅ 成功抓到新聞！(共 {len(feed.entries)} 則)")
                news_items = []
                # 取前 8 條新聞
                for entry in feed.entries[:8]:
                    title = entry.title
                    
                    # 嘗試抓取摘要 (Google News 的摘要通常在 description 裡，含有 HTML)
                    raw_summary = getattr(entry, 'summary', '') or getattr(entry, 'description', '')
                    
                    # 使用 BeautifulSoup 清洗 HTML 標籤，只留純文字
                    clean_summary = ""
                    if raw_summary:
                        soup = BeautifulSoup(raw_summary, "html.parser")
                        clean_summary = soup.get_text(separator=' ', strip=True)
                        # 限制摘要長度，避免 token 爆掉
                        if len(clean_summary) > 200: 
                            clean_summary = clean_summary[:200] + "..."

                    # 組合標題與摘要給 AI 讀
                    item_text = f"Title: {title}\nSummary: {clean_summary}\n"
                    news_items.append(item_text)
                    
                return "\n-----------------\n".join(news_items)
        
        return "⚠️ 今日無重大頭條 (所有新聞來源皆無回應)"
            
    except Exception as e:
        print(f"❌ 新聞抓取系統故障: {e}")
        return "新聞抓取失敗"

# --- 抓 AAII 散戶情緒 ---
def get_aaii_sentiment():
    print("🕵️ 抓取 AAII 散戶情緒...")
    try:
        url = "https://www.aaii.com/sentimentsurvey"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        r = requests.get(url, headers=headers, timeout=10)
        
        if r.status_code == 200:
            text = r.text
            match = re.search(r'(\d{1,2}/\d{1,2}/\d{2,4}).*?(\d{1,2}\.\d)%', text)
            if match:
                date_str = match.group(1)
                bullish_val = float(match.group(2))
                try:
                    dt = pd.to_datetime(date_str)
                    short_date = dt.strftime("%m/%d")
                except:
                    short_date = date_str
                print(f"✅ AAII: {bullish_val}% ({short_date})")
                return bullish_val, short_date
        return None, None
    except:
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
    except:
        return None

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
            
        # 1. 外部真實數據
        aaii_bullish, aaii_date = get_aaii_sentiment()
        cnn_score = get_cnn_fear_greed()
        
        # 2. 替代指標
        delta = df_calc['SPY'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]

        ma_20 = df_calc['SPY'].rolling(window=20).mean().iloc[-1]
        bias = ((latest['SPY'] - ma_20) / ma_20) * 100
        
        # 整合數據
        if aaii_bullish is not None:
            aaii_display = f"{aaii_bullish}% ({aaii_date})"
            aaii_src = "真實數據"
        else:
            aaii_display = f"{current_rsi:.1f} (RSI模擬)"
            aaii_src = "RSI替代"

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
            'aaii_src': aaii_src,
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
    - AAII 散戶情緒: {data['aaii_display']} (參考: >45% 貪婪，<25% 恐慌)
    - CNN 恐懼貪婪: {data['cnn_display']} (參考: <25 恐懼, >75 貪婪)
    - VIX 恐慌指數: {data['vix']:.2f}
    - 市場廣度 (RSP/SPY): {data['breadth']:.4f}
    - Fed Rate: {data['fed_rate']:.2f}%

    【新聞輸入 (含摘要)】
    {news_text}

    【報告輸出格式】
    請嚴格遵守以下 Markdown 格式：

    # 🦅 {data['date']} 全方位投資策略分析

    ## 1. 最新市場體檢報告
    (請建立 Markdown Code Block 表格，保持對齊)
    ```text
    指標            數值               歷史位階/狀態       解讀
    -------------------------------------------------------------------------
    AAII 散戶情緒   {data['aaii_display']}       (請判斷)          (一句話解讀)
    VIX 恐慌指數    {data['vix']:.2f}              (請判斷)          (一句話解讀)
    CNN 恐懼貪婪    {data['cnn_display']}              (請判斷)          (一句話解讀)
    市場廣度        {data['breadth']:.3f}              (請判斷)          (一句話解讀)
    Fed Rate (利率) {data['fed_rate']:.2f}%              (請判斷)          (一句話解讀)
    ```

    ## 2. 📰 當日重大財經新聞
    (請根據我提供的【新聞輸入】，歸納出 3 點最重要的市場驅動因素。**注意：必須包含具體的新聞內容摘要，而不僅僅是標題**)
    * **[新聞標題]**: 這裡請寫出簡短的新聞摘要 (Summary)，解釋這則新聞發生了什麼事以及對市場的影響...
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

# --- 主程式 ---
if __name__ == "__main__":
    TG_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    CHAT_ID = os.environ.get('CHAT_ID')
    API_KEY = os.environ.get('GEMINI_API_KEY')
    
    if TG_TOKEN and CHAT_ID and API_KEY:
        try:
            configure_genai(API_KEY)
            m_data = get_market_data()
            if m_data:
                news = get_financial_news()
                report = generate_ai_report(m_data, news)
                
                # 自動降級發送機制
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                payload = {'chat_id': CHAT_ID, 'text': report, 'parse_mode': 'Markdown'}
                print("📤 發送 Markdown 報告...")
                response = requests.post(url, data=payload)
                
                if response.status_code != 200:
                    print(f"⚠️ Markdown 發送失敗 ({response.text})，改用純文字重發...")
                    payload['parse_mode'] = ''
                    requests.post(url, data=payload)
                    print("✅ 純文字報告已補寄")
                else:
                    print("✅ 報告發送成功")
            else:
                print("⚠️ 數據抓取為空")
        except Exception as e:
            print(f"❌ 執行錯誤: {e}")
            try:
                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                            data={'chat_id': CHAT_ID, 'text': f"Bot Error: {e}"})
            except: pass
    else:
        print("⚠️ 缺少環境變數")
