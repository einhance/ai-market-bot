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

# --- 【精準狙擊版】抓 AAII 完整數據 ---
def get_aaii_sentiment():
    print("🕵️ 抓取 AAII 數據 (精準 Class 定位)...")
    url = "https://www.aaii.com/sentimentsurvey"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com/"
    }
    
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            print(f"⚠️ AAII 連線被拒 (Status: {r.status_code})")
            return None, None

        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 根據你提供的 HTML 結構，我們直接鎖定特定的 class
        # <div class="bar bullish" style="width:49.5%">49.5%</div>
        
        bull_div = soup.find("div", class_="bar bullish")
        neut_div = soup.find("div", class_="bar neutral")
        bear_div = soup.find("div", class_="bar bearish")
        date_div = soup.find("div", class_="date") # <div class="date">1/14/2026</div>

        if bull_div and neut_div and bear_div:
            # 使用 .get_text(strip=True) 確保只抓文字內容，不管 style
            bull = bull_div.get_text(strip=True).replace('%', '')
            neut = neut_div.get_text(strip=True).replace('%', '')
            bear = bear_div.get_text(strip=True).replace('%', '')
            
            # 抓取日期
            date_str = date_div.get_text(strip=True) if date_div else "N/A"
            
            # 格式化日期
            try:
                dt = pd.to_datetime(date_str)
                short_date = dt.strftime("%m/%d")
            except:
                short_date = date_str

            # 驗算一下是否總和約為 100 (避免抓到空值)
            try:
                if float(bull) + float(neut) + float(bear) > 99:
                    full_str = f"Bull:{bull}% Neut:{neut}% Bear:{bear}% ({short_date})"
                    print(f"✅ AAII 抓取成功: {full_str}")
                    return full_str, "真實數據"
            except:
                pass

        print("⚠️ AAII 頁面解析完成，但未找到對應 class (可能是網頁改版)")
        return None, None
            
    except Exception as e:
        print(f"⚠️ AAII 處理錯誤: {e}")
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
        aaii_str, aaii_src = get_aaii_sentiment()
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
        
        # 整合數據 - AAII
        if aaii_str is not None:
            aaii_display = aaii_str
            aaii_source = "真實數據"
        else:
            aaii_display = f"RSI:{current_rsi:.1f} (模擬數值)"
            aaii_source = "RSI替代"

        # 整合數據 - CNN
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
    (請建立 Markdown Code Block 表格，**AAII 數值較長，請確保表格寬度足夠**，不要換行)
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
    else:
        print("⚠️ 缺少環境變數")
