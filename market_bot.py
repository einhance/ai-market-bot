import os
import yfinance as yf
import google.generativeai as genai
import feedparser
import datetime
import requests
import time
import pandas as pd  # 核心修復：引入 Pandas 處理數據缺漏

# --- 設定 Gemini ---
def configure_genai(api_key):
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        print(f"⚠️ Gemini 設定失敗: {e}")

# --- 抓新聞 (RSS) ---
def get_financial_news():
    # 使用 Google News US Business 版面
    rss_url = "https://news.google.com/rss/topics/CAAqJggBCiCPASowCAqXAg8KCOgDPQkKBAgCGAISBAgBEgISBAgQEgIIABIECAESBAgBEg?hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            return "今日無重大頭條"
        # 取前 8 條新聞標題
        headlines = [f"- {entry.title}" for entry in feed.entries[:8]]
        return "\n".join(headlines)
    except:
        return "新聞抓取失敗"

# --- 抓數據 (增強版：自動修復 NaN) ---
def get_market_data():
    tickers = ['^VIX', 'SPY', 'RSP', 'QQQ', 'IWM', '^TNX', 'SOXX'] 
    print("📥 正在下載市場數據...")
    try:
        # 下載過去 5 天的數據 (避免只抓 1 天遇到假日或數據延遲變全空)
        # actions=False 避免股利分割造成欄位格式混亂
        df = yf.download(tickers, period='5d', progress=False, actions=False)['Close']
        
        if df.empty:
            raise Exception("下載失敗：數據表為空")

        # 【核心修復 1】向前填補 (Forward Fill)
        # 如果今天 TNX 沒數據，自動拿昨天的來補，避免 nan
        df = df.ffill()
        
        # 【核心修復 2】尋找最後一個有效交易日
        # 有時候 yfinance 會回傳今天的日期但整行都是 NaN (因為盤前或剛開盤)
        # 我們檢查 SPY 是否為空，如果是，就往前找一天
        latest = df.iloc[-1]
        
        if pd.isna(latest['SPY']):
            print("⚠️ 檢測到最新一行數據為空，自動回溯至前一交易日...")
            latest = df.iloc[-2]
            prev = df.iloc[-3]
        else:
            prev = df.iloc[-2]

        # 計算漲跌幅 (防呆機制：如果分母是 NaN 或 0，回傳 0)
        def calc_change(current, previous):
            if pd.isna(previous) or previous == 0:
                return 0.0
            return ((current - previous) / previous) * 100

        changes = {
            'SPY': calc_change(latest['SPY'], prev['SPY']),
            'QQQ': calc_change(latest['QQQ'], prev['QQQ']),
            'IWM': calc_change(latest['IWM'], prev['IWM']),
            'SOXX': calc_change(latest['SOXX'], prev['SOXX']),
            'RSP': calc_change(latest['RSP'], prev['RSP'])
        }
        
        # 市場廣度
        breadth_ratio = latest['RSP'] / latest['SPY'] if latest['SPY'] else 0
        
        # 使用 .name.date() 確保顯示的是數據那一天的真實日期
        data_date = latest.name.date()

        return {
            'date': data_date,
            'vix': latest['^VIX'] if not pd.isna(latest['^VIX']) else 0,
            'tnx': latest['^TNX'] if not pd.isna(latest['^TNX']) else 0,
            'spy': latest['SPY'],
            'spy_chg': changes['SPY'],
            'qqq_chg': changes['QQQ'],
            'iwm_chg': changes['IWM'],
            'soxx_chg': changes['SOXX'],
            'breadth': breadth_ratio,
            'rsp_chg': changes['RSP']
        }
    except Exception as e:
        print(f"❌ 數據抓取嚴重錯誤: {e}")
        # 在本機跑的時候印出詳細錯誤，方便除錯
        import traceback
        traceback.print_exc()
        return None

# --- 生成報告 (生存模式：自動尋找可用模型) ---
def generate_ai_report(data, news_text):
    
    print("🔍 正在向 Google 查詢可用模型清單...")
    all_models = []
    try:
        # 1. 抓取所有模型
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                all_models.append(m.name)
    except Exception as e:
        return f"❌ 無法連線至 Google API，請檢查網路或 Key: {e}"

    if not all_models:
        return "❌ 你的 API Key 權限下沒有任何可用的模型 (List is empty)。"

    # 2. 智能排序策略 (優先順序邏輯)
    # 策略：Flash (免費/快) > 1.5 Pro > 其他
    # 這樣可以避免一開始就撞到 2.5 Pro 的付費牆
    def priority_sort(name):
        name = name.lower()
        if 'flash' in name and '1.5' in name: return 0  # 最優先：1.5 Flash
        if 'flash' in name: return 1                    # 次優先：其他 Flash (如 2.0 flash exp)
        if 'pro' in name and '1.5' in name: return 2    # 再次：1.5 Pro
        return 3                                        # 最後：其他 (如 2.5 Pro 或舊版)

    all_models.sort(key=priority_sort)
    print(f"📋 測試順序 (前5名): {all_models[:5]}")

    prompt = f"""
    你是一位華爾街資深量化投資策略師。請根據以下數據與新聞，用「繁體中文」寫一份深度市場分析日報。

    【今日數據】
    - 日期: {data['date']}
    - VIX 恐慌指數: {data['vix']:.2f} (若 >20 為恐慌, <13 為過度樂觀)
    - 10年期公債殖利率 (TNX): {data['tnx']:.2f}%
    - SPY (標普500) 漲跌: {data['spy_chg']:.2f}%
    - QQQ (那斯達克) 漲跌: {data['qqq_chg']:.2f}%
    - SOXX (半導體) 漲跌: {data['soxx_chg']:.2f}% (關鍵科技指標)
    - RSP (等權重) 漲跌: {data['rsp_chg']:.2f}%
    - RSP/SPY 市場廣度: {data['breadth']:.4f} (若數值下降代表漲勢集中在權值股)

    【財經新聞頭條】
    {news_text}

    【報告結構要求】
    1. **標題**: 必須包含 Emoji 的吸睛標題 (例如 🦅 🐻 🐂)。
    2. **市場敘事 (Narrative)**: 
       - 結合「新聞事件」與「殖利率/VIX」解釋今日走勢。
       - 特別點評半導體 (SOXX) 與市場廣度。
    3. **紅綠燈號策略**: 
       - 給出 🟢(偏多) / 🟡(中性/震盪) / 🔴(偏空/避險) 燈號。
    4. **操作建議**: 給出 3 點具體建議 (例如現金水位、關注板塊、避險需求)。
    
    請直接輸出 Markdown 格式，不需其他廢話。
    """

    # 3. 大逃殺迴圈：試到成功為止
    last_error = ""
    for model_name in all_models:
        try:
            print(f"🤖 嘗試使用模型: {model_name} ...")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            
            # 成功了！
            print(f"✅ 成功生成！使用模型: {model_name}")
            return f"{response.text}\n\n_(Generated by {model_name})_"
            
        except Exception as e:
            # 失敗了 (可能是 429 Quota, 404 Not Found)
            # 記錄錯誤，休息一下，試下一個
            error_msg = str(e)
            print(f"   ⚠️ 失敗: {error_msg.split('details')[0]}...") 
            last_error = error_msg
            time.sleep(1) # 冷卻 1 秒
            continue
            
    # 如果清單裡幾十個模型全掛了
    return f"❌ 所有模型皆嘗試失敗。最後一次錯誤: {last_error}"

# --- 主程式 (GitHub Actions 進入點) ---
# 注意：如果你用 daily_runner.py 跑，這一段不會被執行，而是執行 daily_runner 的邏輯
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
                
                # 發送 Telegram
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                payload = {'chat_id': CHAT_ID, 'text': report, 'parse_mode': 'Markdown'}
                requests.post(url, data=payload)
                print("✅ [GitHub] 報告發送成功")
            else:
                print("⚠️ [GitHub] 數據抓取為空")
        except Exception as e:
            err_msg = f"❌ [GitHub] 執行錯誤: {e}"
            print(err_msg)
    else:
        print("⚠️ 缺少環境變數 (這是 GitHub Actions 模式，若在本機請使用 daily_runner.py)")
