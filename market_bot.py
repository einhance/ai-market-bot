import os
import yfinance as yf
import google.generativeai as genai
import requests
import datetime
import feedparser # 新增這個套件用來抓新聞

# --- 1. 設定與讀取金鑰 ---
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
CHAT_ID = os.environ.get('CHAT_ID')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

# 設定 Gemini
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-pro')

# --- 2. 抓取 Google 財經新聞 (RSS) ---
def get_financial_news():
    print("正在抓取財經新聞...")
    # 使用 Google News US Business Section 的 RSS Feed
    rss_url = "https://news.google.com/rss/topics/CAAqJggBCiCPASowCAqXAg8KCOgDPQkKBAgCGAISBAgBEgISBAgQEgIIABIECAESBAgBEg?hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(rss_url)
    
    news_summary = []
    # 只取前 8 則頭條，避免資訊過載
    for entry in feed.entries[:8]:
        news_summary.append(f"- {entry.title}")
    
    return "\n".join(news_summary)

# --- 3. 抓取市場數據 ---
def get_market_data():
    print("正在抓取市場數據...")
    tickers = ['^VIX', 'SPY', 'RSP', 'QQQ', 'IWM', '^TNX'] 
    # 加入 ^TNX (10年期公債殖利率) 因為它常是影響股市的主因
    
    df = yf.download(tickers, period='1mo', progress=False)['Close']
    
    latest = df.iloc[-1]
    prev = df.iloc[-2]
    
    changes = ((latest - prev) / prev) * 100
    breadth_ratio = latest['RSP'] / latest['SPY']
    
    return {
        'date': datetime.date.today(),
        'vix': latest['^VIX'],
        'spy': latest['SPY'],
        'qqq': latest['QQQ'],
        'iwm': latest['IWM'],
        'tnx': latest['^TNX'], # 殖利率
        'breadth': breadth_ratio,
        'spy_chg': changes['SPY'],
        'qqq_chg': changes['QQQ'],
        'iwm_chg': changes['IWM']
    }

# --- 4. 呼叫 Gemini 生成綜合分析報告 ---
def generate_ai_report(data, news_text):
    print("正在請求 Gemini 進行綜合分析...")
    
    # 升級版 Prompt：要求結合新聞與數據
    prompt = f"""
    你是一位華爾街資深投資策略師。請閱讀以下的【今日數據】與【今日財經頭條(英文)】，
    為我撰寫一份「繁體中文」的深度市場分析日報。

    【今日數據】
    - 日期: {data['date']}
    - VIX 恐慌指數: {data['vix']:.2f}
    - 10年期公債殖利率: {data['tnx']:.2f}%
    - SPY (標普500): {data['spy']:.2f} (漲跌: {data['spy_chg']:.2f}%)
    - QQQ (那斯達克): 漲跌 {data['qqq_chg']:.2f}%
    - IWM (羅素2000): 漲跌 {data['iwm_chg']:.2f}%
    - 市場廣度 (RSP/SPY): {data['breadth']:.4f} (若數值下降代表巨頭領漲、廣度變差)

    【今日財經頭條 (請從中篩選影響市場的關鍵)】
    {news_text}

    【報告撰寫要求】
    1. **標題**: 使用 Emoji，例如 "🦅 2026-01-06 市場全景分析"
    2. **市場敘事 (Market Narrative)**: 
       - 不要只是列出新聞。請分析**「新聞」如何導致了今天的「數據變化」**。
       - 例如：如果殖利率 (TNX) 升高且新聞提到 Fed 官員發言，請解釋這如何壓抑了科技股 (QQQ)。
    3. **關鍵指標解讀**:
       - VIX 與 市場廣度 的狀態是健康的嗎？有無背離訊號？
    4. **綜合策略紅綠燈**:
       - 給出 🟢(偏多) / 🟡(中性/防禦) / 🔴(偏空) 燈號。
    5. **操作建議**:
       - 針對目前局勢，給出 3 點具體建議（例如：關注特定板塊、增加現金部位、或適合做多/做空）。

    請用專業、簡潔的 Markdown 格式輸出，直接寫內容，不用客套話。
    """
    
    response = model.generate_content(prompt)
    return response.text

# --- 5. 發送到 Telegram ---
def send_telegram(message):
    print("正在發送 Telegram...")
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,
        'text': message,
        'parse_mode': 'Markdown'
    }
    requests.post(url, data=payload)

# --- 主程序 ---
if __name__ == "__main__":
    try:
        # 1. 獲取數據
        market_data = get_market_data()
        # 2. 獲取新聞
        news_headlines = get_financial_news()
        # 3. AI 分析
        ai_report = generate_ai_report(market_data, news_headlines)
        # 4. 發送
        send_telegram(ai_report)
        
        print("✅ 深度分析報告已發送！")
    except Exception as e:
        print(f"❌ 發生錯誤: {e}")
        send_telegram(f"⚠️ Bot 執行錯誤: {e}")
