import os
import yfinance as yf
import google.generativeai as genai
import feedparser
import datetime
import requests

# --- 自動選擇最佳模型 (已加入 Gemini 3.0 Pro) ---
def get_best_model():
    """自動尋找當前 API Key 可用的最佳模型，優先使用付費版 3.0 Pro"""
    print("正在搜尋可用模型...")
    try:
        # 列出所有可用模型
        available_models = []
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        
        print(f"你的 Key 可用的模型清單: {available_models}")
        
        # --- 優先順序策略 (Priority List) ---
        # 1. 優先尋找 Gemini 3.0 Pro (付費/最新版)
        for model in available_models:
            if "gemini-3.0-pro" in model: return model
        for model in available_models:
            if "gemini-3.0" in model: return model
            
        # 2. 其次尋找 Gemini 1.5 Pro
        for model in available_models:
            if "gemini-1.5-pro" in model: return model
            
        # 3. 再來尋找標準版 Pro
        for model in available_models:
            if "gemini-pro" in model: return model
            
        # 4. 最後尋找 Flash (速度快但分析較淺)
        for model in available_models:
            if "gemini-1.5-flash" in model: return model
        for model in available_models:
            if "flash" in model: return model
            
        # 5. 如果都沒對應到，就回傳清單中的第一個
        if available_models:
            return available_models[0]
        
        # 6. 萬一真的什麼都沒抓到，只好盲猜一個最可能的名稱
        return "models/gemini-1.5-pro-latest" 
        
    except Exception as e:
        print(f"搜尋模型失敗: {e}，將使用預設模型")
        return "gemini-pro"

# --- 設定 Gemini ---
def configure_genai(api_key):
    genai.configure(api_key=api_key)

# --- 抓新聞 ---
def get_financial_news():
    rss_url = "https://news.google.com/rss/topics/CAAqJggBCiCPASowCAqXAg8KCOgDPQkKBAgCGAISBAgBEgISBAgQEgIIABIECAESBAgBEg?hl=en-US&gl=US&ceid=US:en"
    try:
        feed = feedparser.parse(rss_url)
        if not feed.entries:
            return "今日無重大頭條"
        headlines = [f"- {entry.title}" for entry in feed.entries[:8]]
        return "\n".join(headlines)
    except:
        return "新聞抓取失敗"

# --- 抓數據 ---
def get_market_data():
    tickers = ['^VIX', 'SPY', 'RSP', 'QQQ', 'IWM', '^TNX', 'SOXX'] 
    try:
        df = yf.download(tickers, period='1mo', progress=False)['Close']
        if df.empty:
            raise Exception("無法下載數據")
            
        latest = df.iloc[-1]
        prev = df.iloc[-2]
        changes = ((latest - prev) / prev) * 100
        breadth_ratio = latest['RSP'] / latest['SPY']
        
        return {
            'date': datetime.date.today(),
            'vix': latest['^VIX'],
            'tnx': latest['^TNX'],
            'spy': latest['SPY'],
            'spy_chg': changes['SPY'],
            'qqq_chg': changes['QQQ'],
            'iwm_chg': changes['IWM'],
            'soxx_chg': changes['SOXX'],
            'breadth': breadth_ratio,
            'rsp_chg': changes['RSP']
        }
    except Exception as e:
        print(f"數據抓取錯誤: {e}")
        return None

# --- 生成報告 ---
def generate_ai_report(data, news_text):
    # 自動選擇模型 (這裡會去呼叫上面的新邏輯)
    model_name = get_best_model()
    print(f"🤖 決定使用的模型是: {model_name}")
    
    model = genai.GenerativeModel(model_name)
    
    prompt = f"""
    你是一位華爾街資深投資策略師。請根據以下數據與新聞，用「繁體中文」寫一份深度市場分析日報。
    
    【使用模型版本】: {model_name} (請發揮你最強的推理能力)

    【今日數據】
    - 日期: {data['date']}
    - VIX 恐慌指數: {data['vix']:.2f}
    - 10年期公債殖利率 (TNX): {data['tnx']:.2f}%
    - SPY (標普500) 漲跌: {data['spy_chg']:.2f}%
    - QQQ (那斯達克) 漲跌: {data['qqq_chg']:.2f}%
    - SOXX (半導體) 漲跌: {data['soxx_chg']:.2f}%
    - RSP (等權重) 漲跌: {data['rsp_chg']:.2f}%
    - RSP/SPY 市場廣度: {data['breadth']:.4f}

    【財經新聞頭條】
    {news_text}

    【報告要求】
    1. **標題**: 帶有 Emoji 的吸睛標題。
    2. **市場敘事 (Market Narrative)**: 
       - 深入分析「新聞事件」與「殖利率/匯率」如何影響了今天的股價。
       - 不要只描述漲跌，要解釋「為什麼」。
    3. **關鍵指標解讀**: 
       - 觀察 VIX 與 市場廣度 是否出現背離或異常。
    4. **綜合策略紅綠燈**: 
       - 給出 🟢(偏多) / 🟡(中性/防禦) / 🔴(偏空) 燈號。
    5. **操作建議**: 
       - 給出 3 點具體建議 (例如：資金控管、避險、或關注特定板塊)。
    
    請直接輸出 Markdown 格式內容。
    """
    
    response = model.generate_content(prompt)
    return response.text

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
                requests.post(url, data=payload)
                print("✅ 報告發送成功")
            else:
                requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                            data={'chat_id': CHAT_ID, 'text': "⚠️ 數據抓取失敗，請檢查 Log"})
        except Exception as e:
            err_msg = f"❌ Bot 執行錯誤: {e}"
            print(err_msg)
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                        data={'chat_id': CHAT_ID, 'text': err_msg})
    else:
        print("⚠️ 缺少環境變數，請檢查 GitHub Secrets")
