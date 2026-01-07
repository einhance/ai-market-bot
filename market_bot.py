import os
import yfinance as yf
import google.generativeai as genai
import feedparser
import datetime
import requests
import time

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

# --- 生成報告 (鎖定最穩定模型) ---
def generate_ai_report(data, news_text):
    
    # 這裡我們強制使用 gemini-1.5-flash
    # 這是目前免費額度最寬裕的模型，最不容易報錯
    target_model = "gemini-1.5-flash"
    
    print(f"🤖 正在嘗試使用模型: {target_model} ...")
    
    prompt = f"""
    你是一位華爾街資深投資策略師。請根據以下數據與新聞，用「繁體中文」寫一份深度市場分析日報。

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
    2. **市場敘事**: 分析新聞與殖利率如何影響今日股價。
    3. **關鍵指標**: 解讀 VIX 與 市場廣度。
    4. **綜合策略紅綠燈**: 🟢/🟡/🔴 燈號。
    5. **操作建議**: 3 點具體建議。
    請直接輸出 Markdown 格式。
    """

    try:
        model = genai.GenerativeModel(target_model)
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        # 如果失敗，回傳詳細錯誤訊息給 Bot，方便我們除錯
        error_msg = f"⚠️ 模型調用失敗: {str(e)}"
        print(error_msg)
        return error_msg

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
                # 呼叫報告生成
                report = generate_ai_report(m_data, news)
                
                url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
                payload = {'chat_id': CHAT_ID, 'text': report, 'parse_mode': 'Markdown'}
                requests.post(url, data=payload)
                print("✅ 執行結束")
            else:
                print("⚠️ 數據抓取為空")
        except Exception as e:
            err_msg = f"❌ Bot 執行嚴重錯誤: {e}"
            print(err_msg)
            requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", 
                        data={'chat_id': CHAT_ID, 'text': err_msg})
    else:
        print("⚠️ 缺少環境變數")
