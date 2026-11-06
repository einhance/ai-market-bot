import pandas as pd
import datetime
import requests
from io import StringIO

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

def fetch_fred(series_ids, start_date, end_date):
    """直接從 FRED 下載 CSV (取代已停止維護的 pandas_datareader)。"""
    frames = []
    for sid in series_ids:
        params = {
            "id": sid,
            "cosd": start_date.strftime("%Y-%m-%d"),
            "coed": end_date.strftime("%Y-%m-%d"),
        }
        r = requests.get(FRED_CSV_URL, params=params, timeout=30,
                         headers={"User-Agent": "Mozilla/5.0 (ai-market-bot)"})
        r.raise_for_status()
        s = pd.read_csv(StringIO(r.text), index_col=0, parse_dates=True, na_values=".")
        s.columns = [sid]
        frames.append(s[sid].astype(float))
    return pd.concat(frames, axis=1).sort_index()

def get_liquidity_monitor():
    # 1. 設定時間範圍 (抓取過去 1 年以計算趨勢)
    start_date = datetime.datetime.now() - datetime.timedelta(days=400)
    end_date = datetime.datetime.now()
    
    print("正在從 FRED 資料庫抓取流動性數據 (Fed Assets, TGA, RRP)...")
    
    try:
        # 2. 從 FRED 抓取三個關鍵變數
        # WALCL: Fed Total Assets (週資料, 通常週四更新)
        # WTREGEN: Treasury General Account (日資料)
        # RRPONTSYD: Overnight Reverse Repurchase Agreements (日資料)
        
        indicators = ['WALCL', 'WTREGEN', 'RRPONTSYD']
        data = fetch_fred(indicators, start_date, end_date)
        
        # 3. 數據清洗與對齊
        # 因為 WALCL 是週資料，其他是日資料，會有 NaN。
        # 我們使用 forward fill (ffill) 填補空缺，讓每天都有數據方便計算
        data = data.ffill().dropna()
        
        # 單位轉換：原始數據單位不統一，通常轉為「十億美元 (Billions)」
        # WALCL 是 Millions (百萬)，除以 1000 變 Billions
        # WTREGEN 是 Billions，不動
        # RRPONTSYD 是 Billions，不動
        
        df = pd.DataFrame()
        df['Fed_Assets'] = data['WALCL'] / 1000 # 轉為 Billions
        df['TGA'] = data['WTREGEN'] / 1000      # 轉為 Billions
        df['RRP'] = data['RRPONTSYD']           # 已經是 Billions
        
        # 4. 計算 Net Liquidity (淨流動性)
        # 公式: Fed Assets - TGA - RRP
        df['Net_Liquidity'] = df['Fed_Assets'] - df['TGA'] - df['RRP']
        
        return df
        
    except Exception as e:
        print(f"數據抓取失敗: {e}")
        return None

def liquidity_signal(df):
    """以 4 週趨勢為主、1 週變化為確認的流動性訊號。回傳 dict 供燈號模型使用。"""
    if df is None or len(df) < 2:
        return None
    cur = df.iloc[-1]
    p1 = df.iloc[-6] if len(df) >= 6 else df.iloc[0]
    p4 = df.iloc[-21] if len(df) >= 21 else df.iloc[0]
    chg_1w = cur['Net_Liquidity'] - p1['Net_Liquidity']
    chg_4w = cur['Net_Liquidity'] - p4['Net_Liquidity']
    # 排除 TGA 的流動性 (Fed 資產 - RRP)：TGA 受稅季/發債影響大，單獨拆開看
    ex_tga_4w = (cur['Fed_Assets'] - cur['RRP']) - (p4['Fed_Assets'] - p4['RRP'])
    tga_effect_4w = -(cur['TGA'] - p4['TGA'])   # TGA 下降 = 釋出流動性 (正值)

    # 4 週趨勢評分 (-2 ~ +2)
    if chg_4w > 50: score = 2
    elif chg_4w > 20: score = 1
    elif chg_4w < -50: score = -2
    elif chg_4w < -20: score = -1
    else: score = 0
    # 1 週方向相反且幅度 > 200 億 → 訊號往中性靠一級
    if score > 0 and chg_1w < -20: score -= 1
    if score < 0 and chg_1w > 20: score += 1
    # 4 週持平但 1 週明顯變化 → 僅給半級提示 (不改分數)，由文字標示
    labels = {2: "🟢 強力寬鬆", 1: "🟢 寬鬆", 0: "🟡 中性", -1: "🔴 緊縮", -2: "🔴 強力緊縮"}
    return {
        'level': cur['Net_Liquidity'], 'chg_1w': chg_1w, 'chg_4w': chg_4w,
        'ex_tga_4w': ex_tga_4w, 'tga_effect_4w': tga_effect_4w,
        'score': score, 'label': labels[score],
    }

def analyze_changes(df):
    if df is None: return

    # 取得最新一天的數據
    current = df.iloc[-1]
    
    # 取得 1 週前 (5個交易日) 和 4 週前 (20個交易日)
    try:
        prev_1w = df.iloc[-6] 
        prev_4w = df.iloc[-21]
    except:
        prev_1w = df.iloc[0]
        prev_4w = df.iloc[0]

    # 定義要分析的項目
    metrics = {
        'Net_Liquidity': {'name': '淨流動性 (Net Liq)', 'bullish_if': 'up'},
        'Fed_Assets':    {'name': '聯準會資產 (Assets)', 'bullish_if': 'up'},
        'TGA':           {'name': '財政部帳戶 (TGA)',    'bullish_if': 'down'},
        'RRP':           {'name': '逆回購 (RRP)',       'bullish_if': 'down'}
    }
    
    print("\n" + "="*90)
    print(f"💧 宏觀流動性水位監控 (Smart Signal 版)")
    print(f"日期: {df.index[-1].strftime('%Y-%m-%d')}")
    print("="*90)
    
    # 表頭調整，增加欄位寬度
    print(f"{'指標名稱':<22} {'目前水位':<12} {'1週變化 (關鍵訊號)':<25} {'1月變化':<15}")
    print("-" * 90)
    

    for key, info in metrics.items():
        val_now = current[key]
        change_1w = val_now - prev_1w[key]
        change_4w = val_now - prev_4w[key]
        
        # --- 智能訊號判斷邏輯 ---
        # 設定雜訊過濾門檻 (200億)
        threshold_noise = 20
        # 設定強力訊號門檻 (500億)
        threshold_strong = 50 
        
        # 判斷方向 (是否有利股市)
        is_bullish_direction = (change_1w > 0) if info['bullish_if'] == 'up' else (change_1w < 0)
        
        # 產生訊號文字
        abs_change = abs(change_1w)
        
        if abs_change < threshold_noise:
            signal_str = "🟡中性 (雜訊)"
        elif is_bullish_direction:
            if abs_change > threshold_strong:
                signal_str = "🟢強力寬鬆 (強)"
            else:
                signal_str = "🟢寬鬆"
        else: # Bearish direction
            if abs_change > threshold_strong:
                signal_str = "🔴強力緊縮 (險)"
            else:
                signal_str = "🔴緊縮"

        # 格式化輸出
        print(f"{info['name']:<22} ${val_now:,.0f}B      {change_1w:+,.0f}B {signal_str:<15}   {change_4w:+,.0f}B")

    sig = liquidity_signal(df)
    print("-" * 90)
    print(f"【流動性訊號 (4週趨勢為主)】: {sig['label']}")
    print(f"  淨流動性 4週 {sig['chg_4w']:+,.0f}B / 1週 {sig['chg_1w']:+,.0f}B")
    print(f"  拆解 4週: TGA 貢獻 {sig['tga_effect_4w']:+,.0f}B, 排除TGA (Fed資產-RRP) {sig['ex_tga_4w']:+,.0f}B")
    print("-" * 90)
    print("邏輯說明:")
    print("1. 單項變化量 < 200億: 視為雜訊；> 500億: 強力訊號。")
    print("2. 綜合訊號以淨流動性 4 週變化為主，1 週反向變化會將訊號降一級。")
    print("3. TGA 受稅季與發債影響，短期波動大，已單獨拆解。")
    print("="*90)

if __name__ == "__main__":
    df = get_liquidity_monitor()
    analyze_changes(df)
