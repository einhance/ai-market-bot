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
# 分開匯入：其中一個模組壞掉時，另一個仍可正常執行
try:
    import liquidity_tracker
    LIQ_AVAILABLE = True
except Exception as e:
    print(f"⚠️ liquidity_tracker 匯入失敗，流動性分析將略過: {e!r}")
    LIQ_AVAILABLE = False

try:
    import sector_flow
    SEC_AVAILABLE = True
except Exception as e:
    print(f"⚠️ sector_flow 匯入失敗，資金流向分析將略過: {e!r}")
    SEC_AVAILABLE = False

MODULES_AVAILABLE = LIQ_AVAILABLE or SEC_AVAILABLE

import regime

# --- 設定 Gemini ---
def configure_genai(api_key):
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        print(f"⚠️ Gemini 設定失敗: {e}")

# --- 抓新聞 ---
NEWS_FAILED = "⚠️ 新聞抓取失敗 (所有來源皆無回應)"

def get_financial_news(max_items=10):
    # 2026-11: Google News topic 連結回傳 400、Yahoo rssindex 回傳 404，改用以下來源
    rss_sources = [
        ("Google News", "https://news.google.com/rss/search?q=stock+market+when:1d&hl=en-US&gl=US&ceid=US:en"),
        ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114"),
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
        ("Investing.com", "https://www.investing.com/rss/news_25.rss"),
    ]
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                             "(KHTML, like Gecko) Chrome/130 Safari/537.36"}
    per_source = 3
    news_items, seen = [], set()
    for src, url in rss_sources:
        try:
            print(f"📰 抓取新聞: {src} ...")
            r = requests.get(url, headers=headers, timeout=15)
            feed = feedparser.parse(r.content)
            if r.status_code != 200 or not feed.entries:
                print(f"⚠️ {src} 無資料 (HTTP {r.status_code})")
                continue
            count = 0
            for entry in feed.entries:
                title = entry.title.strip()
                key = title.lower()[:60]
                if key in seen: continue
                seen.add(key)
                raw = getattr(entry, 'summary', '') or getattr(entry, 'description', '')
                summary = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)[:200] if raw else ""
                news_items.append(f"[{src}] Title: {title}\nSummary: {summary}\n")
                count += 1
                if count >= per_source: break
            print(f"✅ {src}: {count} 則")
        except Exception as e:
            print(f"❌ {src} 失敗: {e}")
        if len(news_items) >= max_items: break
    if not news_items:
        return NEWS_FAILED
    return "\n-----------------\n".join(news_items[:max_items])

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
        df = yf.download(tickers, period='60d', progress=False, auto_adjust=True)['Close']
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

        # 資料品質檢查：ETF 單日變動 > ±15% 視為分割/資料錯誤，不送進報告
        data_warnings = []
        changes = {}
        for t, key in [('SPY', 'spy_chg'), ('QQQ', 'qqq_chg'), ('SOXX', 'soxx_chg')]:
            c = calc_change(latest[t], prev[t])
            if abs(c) > 15:
                data_warnings.append(f"{t} 單日 {c:+.1f}% 疑似資料錯誤，已排除")
                c = None
            changes[key] = c
        for w in data_warnings: print(f"⚠️ {w}")

        # 廣度改看 RSP/SPY 比值的 20 日變化 (比值本身長期會漂移，固定門檻無意義)
        ratio = (df_calc['RSP'] / df_calc['SPY']).dropna()
        breadth_chg_20d = (ratio.iloc[-1] / ratio.iloc[-21] - 1) * 100 if len(ratio) > 21 else None

        return {
            'date': data_date,
            'vix': latest['^VIX'],
            'tnx': latest['^TNX'],
            'fed_rate': latest['^IRX'],
            'spy': latest['SPY'],
            **changes,
            'breadth': breadth_ratio,
            'breadth_chg_20d': breadth_chg_20d,
            'bias': bias,
            'rsi': current_rsi,
            'cnn_score': cnn_score,
            'data_warnings': data_warnings,
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
            font = ImageFont.truetype("NotoSansTC-Regular.ttf", 14)
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

def _fmt(v, f):
    return f.format(v) if v is not None else '無資料'

# --- 生成報告 ---
def generate_ai_report(data, news_text, liquidity_text="N/A", sector_text="N/A", regime_text="N/A", regime=None):
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
    - 市場廣度 (RSP/SPY 20日變化): {_fmt(data.get('breadth_chg_20d'), '{:+.2f}%')} (正值=資金擴散到中小型/等權股，負值=集中在權值股)
    - 短期利率 (13週國庫券 ^IRX，近似聯邦基金利率): {data['fed_rate']:.2f}%
    - SPY 單日 {_fmt(data.get('spy_chg'), '{:+.2f}%')}、QQQ 單日 {_fmt(data.get('qqq_chg'), '{:+.2f}%')}、SOXX 單日 {_fmt(data.get('soxx_chg'), '{:+.2f}%')}
    - 資料警示: {'; '.join(data.get('data_warnings') or []) or '無'}

    【量化燈號模型 (已由程式計算，不可更改)】
    {regime_text}

    【宏觀流動性數據 (New)】
    {liquidity_text}

    【板塊資金流向數據 (New)】
    {sector_text}

    【新聞頭條】
    {news_text}
    (若上方顯示「新聞抓取失敗」，第 4 節請直接寫「今日新聞來源無法取得」，不要寫成「無重大新聞」，也不要自行編造新聞)

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
    市場廣度(20日)  {_fmt(data.get('breadth_chg_20d'), '{:+.2f}%')}              (請判斷)          (一句話解讀)
    短期利率(13週)  {data['fed_rate']:.2f}%              (請判斷)          (一句話解讀)
    ```

    ## 2. 💧 宏觀流動性分析 (新增)
    * **水位狀態**: (以【宏觀流動性數據】中的「流動性訊號 (4週趨勢為主)」為準)
    * **關鍵變化**: (說明 4 週與 1 週淨流動性變化，並指出有多少來自 TGA 的短期波動)

    ## 3. 🌍 資金流向與熱點 (新增)
    * **全球資金**: (參考【板塊資金流向數據】，錢流向哪個國家？)
    * **強勢板塊**: (列出領漲的美股板塊與細分產業)
    * **風險偏好**: (根據「進攻 vs 防禦」數值，說明資金是追逐成長還是躲進防禦板塊)

    ## 4. 📰 當日重大財經新聞
    (歸納 3 點最重要的市場驅動新聞)
    * **[標題]**: ...
    * **[標題]**: ...
    * **[標題]**: ...

    ## 5. 🚦 綜合投資策略：{regime['light'] if regime else '🟡'} {regime['label'] if regime else '黃燈'}
    (燈號已由【量化燈號模型】決定，**你不可更改燈號**。請先原樣貼出量化燈號模型的分數表 (放在 ```text code block 內)，再用 2-3 句解釋主要是哪些因子造成這個燈號；若情緒註記為極端，說明其逆向意義但不可據此改變燈號)

    **核心觀點**: (一句話總結)

    **操作建議**:
    1.  **資金控管**: (依燈號與流動性訊號建議持股水位)
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
def build_report():
    """抓資料、跑模組、算燈號、產生報告。回傳 (report, image_files)。"""
    m_data = get_market_data()
    if not m_data:
        print("⚠️ 數據抓取為空")
        return None, []

    news = get_financial_news()
    liq_text = sec_text = "數據無法取得"
    liq_sig = risk_app = None
    images = []

    if MODULES_AVAILABLE:
        print("🚀 啟動進階分析模組...")
    if LIQ_AVAILABLE:
        holder = {}
        def run_liq():
            holder['df'] = liquidity_tracker.get_liquidity_monitor()
            liquidity_tracker.analyze_changes(holder['df'])
        liq_text = run_module_and_capture_output(run_liq)
        print(liq_text)  # 同時顯示在 Actions log，方便除錯
        try:
            liq_sig = liquidity_tracker.liquidity_signal(holder.get('df'))
        except Exception as e:
            print(f"⚠️ 流動性訊號計算失敗: {e}")
        img = text_to_image(liq_text, "liq_output.png")
        if img: images.append(img)

    if SEC_AVAILABLE:
        holder = {}
        def run_sec():
            data = sector_flow.download_and_process_data()
            holder['ranks'] = sector_flow.calculate_rankings(data)
            sector_flow.print_aligned_table(holder['ranks'])
        sec_text = run_module_and_capture_output(run_sec)
        print(sec_text)
        try:
            risk_app = sector_flow.risk_appetite(holder.get('ranks'), 20)
        except Exception as e:
            print(f"⚠️ 風險偏好計算失敗: {e}")
        img = text_to_image(sec_text, "sec_output.png")
        if img: images.append(img)

    reg = regime.compute_regime(m_data, liq_sig, risk_app)
    regime_text = regime.format_regime(reg)
    print(regime_text)

    report = generate_ai_report(m_data, news, liq_text, sec_text, regime_text, reg)
    return report, images


if __name__ == "__main__":
    TG_TOKEN = os.environ.get('TELEGRAM_TOKEN')
    CHAT_ID_ENV = os.environ.get('CHAT_ID')
    API_KEY = os.environ.get('GEMINI_API_KEY')
    DRY_RUN = os.environ.get('DRY_RUN', '').lower() in ('1', 'true', 'yes')

    if not API_KEY or (not DRY_RUN and not (TG_TOKEN and CHAT_ID_ENV)):
        print("⚠️ 缺少環境變數")
        sys.exit(1)

    try:
        configure_genai(API_KEY)
        report, images = build_report()
        if not report:
            sys.exit(1)

        if DRY_RUN:
            print("===== DRY RUN：以下報告不會發送到 Telegram =====")
            print(report)
            sys.exit(0)

        chat_ids = [cid.strip() for cid in CHAT_ID_ENV.split(',') if cid.strip()]
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        for cid in chat_ids:
            print(f"📤 發送給 {cid}...")
            payload = {'chat_id': cid, 'text': report, 'parse_mode': 'Markdown'}
            res = requests.post(url, data=payload)
            if res.status_code != 200:
                payload['parse_mode'] = ''
                requests.post(url, data=payload)
            for img in images:
                send_telegram_photo(TG_TOKEN, cid, img)
            time.sleep(1)
    except Exception as e:
        print(f"❌ 錯誤: {e}")
        sys.exit(1)
