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
import cloudscraper
import sys
from io import StringIO
# Add this with your other imports
from PIL import Image, ImageDraw, ImageFont

# --- [NEW] Import Custom Modules ---
try:
    import liquidity_tracker
    import sector_flow
    MODULES_AVAILABLE = True
except ImportError:
    print("⚠️ Warning: liquidity_tracker or sector_flow not found. Advanced analysis will be skipped.")
    MODULES_AVAILABLE = False

# --- 設定 Gemini ---
def configure_genai(api_key):
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        print(f"⚠️ Gemini 設定失敗: {e}")

# --- 抓新聞 ---
def get_financial_news():
    rss_sources = [
        "https://news.google.com/rss/topics/CAAqJggBCiCPASowCAqXAg8KCOgDPQkKBAgCGAISBAgBEgISBAgQEgIIABIECAESBAgBEg?hl=en-US&gl=US&ceid=US:en",
        "https://finance.yahoo.com/news/rssindex"
    ]
    scraper = cloudscraper.create_scraper()
    try:
        for url in rss_sources:
            print(f"📰 抓取新聞: {url} ...")
            response = scraper.get(url, timeout=10)
            feed = feedparser.parse(response.content)
            if feed.entries:
                print(f"✅ 成功抓到 {len(feed.entries)} 則新聞")
                news_items = []
                for entry in feed.entries[:8]:
                    title = entry.title
                    raw_summary = getattr(entry, 'summary', '') or getattr(entry, 'description', '')
                    clean_summary = ""
                    if raw_summary:
                        soup = BeautifulSoup(raw_summary, "html.parser")
                        clean_summary = soup.get_text(separator=' ', strip=True)[:200]
                    news_items.append(f"Title: {title}\nSummary: {clean_summary}\n")
                return "\n-----------------\n".join(news_items)
        return "⚠️ 今日無重大頭條"
    except Exception as e:
        print(f"❌ 新聞抓取失敗: {e}")
        return "新聞抓取失敗"

# --- 【HTML 結構解析 + Spread 計算版】抓 AAII ---
def get_aaii_sentiment():
    print("🕵️ 啟動 AAII 結構化抓取...")
    url = "https://www.aaii.com/sentimentsurvey"
    scraper = cloudscraper.create_scraper()
    
    try:
        r = scraper.get(url, timeout=15)
        if r.status_code != 200:
            print(f"⚠️ AAII 連線失敗 (Code: {r.status_code})")
            return None, None

        soup = BeautifulSoup(r.text, 'html.parser')
        
        # 尋找所有 .weekending 區塊
        week_blocks = soup.find_all("div", class_="weekending")
        
        for block in week_blocks:
            date_div = block.find("div", class_="date")
            if not date_div: continue
            
            date_text = date_div.get_text(strip=True)
            
            # 排除標題行，只找日期開頭是數字的 (如 "1/14/2026")
            if not date_text[0].isdigit(): continue
            
            # 抓取數值
            bull_div = block.find("div", class_="bar bullish")
            neut_div = block.find("div", class_="bar neutral")
            bear_div = block.find("div", class_="bar bearish")
            
            if bull_div and neut_div and bear_div:
                try:
                    bull = float(bull_div.get_text(strip=True).replace('%', ''))
                    neut = float(neut_div.get_text(strip=True).replace('%', ''))
                    bear = float(bear_div.get_text(strip=True).replace('%', ''))
                    
                    # --- 新增：計算 Spread (多空差) ---
                    spread = bull - bear
                    # 格式化 Spread，自動加上 + 或 - 號 (例如 +21.3% 或 -5.0%)
                    spread_str = f"{spread:+.1f}%"

                    # 處理日期
                    try:
                        dt = pd.to_datetime(date_text)
                        short_date = dt.strftime("%m/%d")
                    except:
                        short_date = date_text

                    # 組合最終顯示字串
                    # 格式: Bull:49.5% Bear:28.2% Spread:+21.3% (01/14)
                    full_str = f"Bull:{bull}% Bear:{bear}% Spread:{spread_str} ({short_date})"
                    
                    print(f"✅ AAII 解析成功: {full_str}")
                    return full_str, "真實數據"
                except ValueError:
                    continue

        print("⚠️ 未能解析出 AAII 數值")
        return None, None
            
    except Exception as e:
        print(f"⚠️ AAII 處理錯誤: {e}")
        return None, None

# --- 抓 CNN 指數 ---
def get_cnn_fear_greed():
    print("🕵️ 抓取 CNN ...")
    scraper = cloudscraper.create_scraper()
    try:
        url = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"
        headers = {"Referer": "https://www.cnn.com/"}
        r = scraper.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data['fear_and_greed']['score']
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
        
        # 技術指標計算
        delta = df_calc['SPY'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        current_rsi = rsi.iloc[-1]
        
        ma_20 = df_calc['SPY'].rolling(window=20).mean().iloc[-1]
        bias = ((latest['SPY'] - ma_20) / ma_20) * 100
        
        # 整合數據
        if aaii_str:
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
    
    # --- [NEW] Helper Function to Capture Output ---
def run_module_and_capture_output(module_func):
    """Executes a function and captures its print output as a string."""
    old_stdout = sys.stdout
    result_buffer = StringIO()
    sys.stdout = result_buffer
    try:
        module_func()
    except Exception as e:
        print(f"模組執行錯誤: {e}")
    sys.stdout = old_stdout
    return result_buffer.getvalue()

def text_to_image(text, filename="output.png"):
    if not text: return None
    
    try:
        # Try to load a monospace font (better for tables)
        # On Linux/Mac, this path usually works. If not, it falls back to default.
        try:
            font = ImageFont.truetype("DejaVuSansMono.ttf", 14)
        except:
            font = ImageFont.load_default()

        # Split text into lines to calculate image size
        lines = text.split('\n')
        max_width = max(len(line) for line in lines) * 10  # Approximate width
        total_height = len(lines) * 20  # Approximate height per line
        
        # Create a black image
        image = Image.new('RGB', (max_width + 40, total_height + 40), color=(0, 0, 0))
        draw = ImageDraw.Draw(image)
        
        # Draw text in white
        draw.text((20, 20), text, font=font, fill=(255, 255, 255))
        
        # Save the file
        image.save(filename)
        return filename
    except Exception as e:
        print(f"Error creating image: {e}")
        return None
        
def send_telegram_photo(token, chat_id, file_path):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(file_path, 'rb') as f:
        payload = {'chat_id': chat_id}
        files = {'photo': f}
        requests.post(url, data=payload, files=files)

# --- 生成報告 ---
def generate_ai_report(data, news_text, liquidity_text="N/A", sector_text="N/A"):
    print("🔍 查詢模型...")
    all_models = []
    try:
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                all_models.append(m.name)
    except: return "❌ Google API 連線失敗"
    
    if not all_models: return "❌ 無可用模型"

    # 優先順序: Flash > Pro
    def priority_sort(name):
        name = name.lower()
        if 'flash' in name and '1.5' in name: return 0 
        if 'flash' in name: return 1
        if 'pro' in name and '1.5' in name: return 2
        return 3
    all_models.sort(key=priority_sort)
    
    # --- PROMPT (Original + New Data Injected) ---
    prompt = f"""
    你是一位華爾街量化分析師。請根據以下數據，製作一份「繁體中文」日報。

    【今日關鍵數據】
    - 日期: {data['date']}
    - AAII 散戶情緒: {data['aaii_display']} (來源: {data['aaii_src']})
      (參考: >45% 偏樂觀/貪婪，<25% 偏悲觀/恐慌)
    - CNN 恐懼貪婪: {data['cnn_display']} (來源: {data['cnn_src']})
      (參考: <25 極度恐懼, >75 極度貪婪)
    - VIX 恐慌指數: {data['vix']:.2f}
    - 市場廣度 (RSP/SPY): {data['breadth']:.4f} (低於 0.29 代表極度集中)
    - Fed Rate (基準利率): {data['fed_rate']:.2f}% (使用13週公債代替)

    【宏觀流動性數據 (New)】
    {liquidity_text}

    【板塊資金流向數據 (New)】
    {sector_text}

    【新聞頭條】
    {news_text}

    【報告輸出格式】
    請嚴格遵守以下 Markdown 格式（包含表格）：

    # 🦅 {data['date']} 全方位投資策略分析

    ## 1. 最新市場體檢報告
    (請建立 Markdown Code Block 表格，**欄位必須完全一致**，不要解釋，直接畫表。請保持對齊)
    ```text
    指標            數值               歷史位階/狀態       解讀
    -------------------------------------------------------------------------
    AAII 散戶情緒   {data['aaii_display']}       (請判斷)          (一句話解讀)
    VIX 恐慌指數    {data['vix']:.2f}              (請判斷)          (一句話解讀)
    CNN 恐懼貪婪    {data['cnn_display']}              (請判斷)          (一句話解讀)
    市場廣度        {data['breadth']:.3f}              (請判斷)          (一句話解讀)
    Fed Rate (利率) {data['fed_rate']:.2f}%              (請判斷)          (一句話解讀)
    ```

    ## 2. 💧 宏觀流動性分析 (新增)
    * **水位狀態**: (參考【宏觀流動性數據】，判斷是寬鬆還是緊縮)
    * **關鍵變化**: (簡述 Net Liquidity 和 TGA 的變化)

    ## 3. 🌍 資金流向與熱點 (新增)
    * **全球資金**: (參考【板塊資金流向數據】，錢流向哪個國家？)
    * **強勢板塊**: (列出領漲的美股板塊與細分產業)

    ## 4. 📰 當日重大財經新聞
    (歸納 3 點最重要的市場驅動新聞)
    * **[標題]**: ...
    * **[標題]**: ...
    * **[標題]**: ...

    ## 5. 🚦 綜合投資策略：(請填入 🟢/🟡/🔴) 燈
    (綜合上述「情緒、流動性、資金流」給出燈號)

    **核心觀點**: (一句話總結)

    **操作建議**:
    1.  **資金控管**: (參考流動性水位建議)
    2.  **關注機會**: (參考資金流向建議強勢股)
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
    CHAT_ID_ENV = os.environ.get('CHAT_ID')
    API_KEY = os.environ.get('GEMINI_API_KEY')
    
    if TG_TOKEN and CHAT_ID_ENV and API_KEY:
        try:
            chat_ids = [cid.strip() for cid in CHAT_ID_ENV.split(',') if cid.strip()]
            configure_genai(API_KEY)
            m_data = get_market_data()
            
            if m_data:
                news = get_financial_news()
                # [NEW] Advanced Modules Execution
                liq_text = "數據無法取得"
                sec_text = "數據無法取得"
                
                if MODULES_AVAILABLE:
                    print("🚀 啟動進階分析模組...")
                    # Liquidity
                    def run_liq():
                        df = liquidity_tracker.get_liquidity_monitor()
                        liquidity_tracker.analyze_changes(df)
                    liq_text = run_module_and_capture_output(run_liq)

                    # --- ADD THIS ---
                    liq_image_file = text_to_image(liq_text, "liq_output.png")
                    # ----------------
                    
                    # Sector Flow
                    def run_sec():
                        data = sector_flow.download_and_process_data()
                        ranks = sector_flow.calculate_rankings(data)
                        sector_flow.print_aligned_table(ranks)
                    sec_text = run_module_and_capture_output(run_sec)

                    # --- ADD THIS ---
                    sec_image_file = text_to_image(sec_text, "sec_output.png")
                    # ----------------

                report = generate_ai_report(m_data, news, liq_text, sec_text)
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                
                for cid in chat_ids:
                    print(f"📤 發送給 {cid}...")
                    payload = {'chat_id': cid, 'text': report, 'parse_mode': 'Markdown'}
                    res = requests.post(url, data=payload)
                    if res.status_code != 200:
                        payload['parse_mode'] = ''
                        requests.post(url, data=payload)

                    # --- 2. ADD THIS: Send Images ---
                    # (Add this block right here, before the sleep)
                    if MODULES_AVAILABLE:
                        # Send Liquidity Image if it exists
                        if 'liq_image_file' in locals() and liq_image_file:
                            send_telegram_photo(TG_TOKEN, cid, liq_image_file)
                        
                        # Send Sector Image if it exists
                        if 'sec_image_file' in locals() and sec_image_file:
                            send_telegram_photo(TG_TOKEN, cid, sec_image_file)
                    # --------------------------------
                    time.sleep(1)
            else:
                print("⚠️ 數據抓取為空")
        except Exception as e:
            print(f"❌ 錯誤: {e}")
    else:
        print("⚠️ 缺少環境變數")
