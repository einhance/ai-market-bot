import pandas_datareader.data as web
import pandas as pd
import datetime

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
        data = web.DataReader(indicators, 'fred', start_date, end_date)
        
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
    
    overall_status = "🟡 中性觀察" # 預設狀態

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

        # 如果是 Net Liquidity，這個訊號決定整體市場氣氛
        if key == 'Net_Liquidity':
            if "中性" in signal_str: overall_status = "🟡 中性 (盤整/個股表現)"
            elif "🟢" in signal_str: overall_status = "🟢 綠燈 (適合做多)"
            elif "🔴" in signal_str: overall_status = "🔴 紅燈 (風險趨避)"
            
        # 格式化輸出
        print(f"{info['name']:<22} ${val_now:,.0f}B      {change_1w:+,.0f}B {signal_str:<15}   {change_4w:+,.0f}B")

    print("-" * 90)
    print(f"【綜合操作建議】: {overall_status}")
    print("-" * 90)
    print("邏輯說明:")
    print("1. 變化量 < 200億: 視為市場雜訊，訊號為中性。")
    print("2. 變化量 > 500億: 視為強力訊號，趨勢明確。")
    print("="*90)

if __name__ == "__main__":
    df = get_liquidity_monitor()
    analyze_changes(df)
