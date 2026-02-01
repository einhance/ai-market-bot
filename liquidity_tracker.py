import pandas_datareader.data as web
import pandas as pd
import datetime
import matplotlib.pyplot as plt
import pandas.plotting as plotting

def get_liquidity_monitor():
    # 設定時間範圍 (抓取過去 1 年以計算趨勢)
    start_date = datetime.datetime.now() - datetime.timedelta(days=400)
    end_date = datetime.datetime.now()
    
    print("正在連線 FRED 資料庫抓取流動性數據 (Fed Assets, TGA, RRP)...")
    
    try:
        # 2. 從 FRED 抓取三個關鍵變數
        indicators = ['WALCL', 'WTREGEN', 'RRPONTSYD']
        data = web.DataReader(indicators, 'fred', start_date, end_date)
        
        # 3. 數據清洗與對齊
        data = data.ffill().dropna()
        
        # 單位轉換：轉為「十億美元 (Billions)」
        df = pd.DataFrame()
        df['Fed_Assets'] = data['WALCL'] / 1000 # Millions -> Billions
        df['TGA'] = data['WTREGEN']             # Billions
        df['RRP'] = data['RRPONTSYD']           # Billions
        
        # 4. 計算 Net Liquidity (淨流動性)
        df['Net_Liquidity'] = df['Fed_Assets'] - df['TGA'] - df['RRP']
        
        print("數據抓取成功！正在分析...")
        return df
        
    except Exception as e:
        print(f"數據抓取失敗: {e}")
        print("可能原因：網絡連線問題，或 pandas_datareader 版本過舊。")
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
    # --- 新增公式顯示於此 ---
    print(f"公式: Net Liquidity = Fed Assets - TGA - RRP")
    print("="*90)
    
    # 表頭調整
    print(f"{'指標名稱':<22} {'目前水位':<12} {'1週變化 (關鍵訊號)':<25} {'1月變化':<15}")
    print("-" * 90)
    
    overall_status = "🟡 中性觀察" # 預設狀態

    for key, info in metrics.items():
        val_now = current[key]
        change_1w = val_now - prev_1w[key]
        change_4w = val_now - prev_4w[key]
        
        # --- 智能訊號判斷邏輯 ---
        threshold_noise = 20    # 200億以下視為雜訊
        threshold_strong = 50   # 500億以上視為強力訊號
        
        is_bullish_direction = (change_1w > 0) if info['bullish_if'] == 'up' else (change_1w < 0)
        abs_change = abs(change_1w)
        
        if abs_change < threshold_noise:
            signal_str = "🟡中性 (雜訊)"
        elif is_bullish_direction:
            if abs_change > threshold_strong:
                signal_str = "🟢強力寬鬆 (強)"
            else:
                signal_str = "🟢寬鬆"
        else:
            if abs_change > threshold_strong:
                signal_str = "🔴強力緊縮 (險)"
            else:
                signal_str = "🔴緊縮"

        # 綜合訊號判斷
        if key == 'Net_Liquidity':
            if "中性" in signal_str: overall_status = "🟡 中性 (盤整/個股表現)"
            elif "🟢" in signal_str: overall_status = "🟢 綠燈 (適合做多)"
            elif "🔴" in signal_str: overall_status = "🔴 紅燈 (風險趨避)"
            
        print(f"{info['name']:<22} ${val_now:,.0f}B      {change_1w:+,.0f}B {signal_str:<15}   {change_4w:+,.0f}B")

    print("-" * 90)
    print(f"【綜合操作建議】: {overall_status}")
    print("-" * 90)
    print("邏輯說明: 變化量 > 500億 (顯示為'強'或'險') 為趨勢明確訊號，請務必重視。")
    print("="*90)

def save_liquidity_chart(df, filename="liquidity_table.png"):
    if df is None: return None
    
    # 建立一個簡單的圖表來放表格
    fig, ax = plt.subplots(figsize=(10, 4)) # 調整寬高
    ax.axis('off') # 隱藏坐標軸
    ax.axis('tight')
    
    # 整理要顯示的數據 (取最後一筆與變動量)
    # 這裡為了簡單，我們直接畫出原始數據的最後幾行，或是您分析後的摘要
    # 為了美觀，我們抓出最後 5 週的數據來畫
    display_df = df.tail(5)[['Fed_Assets', 'TGA', 'RRP', 'Net_Liquidity']].sort_index(ascending=False)
    # 格式化數字
    display_df = display_df.applymap(lambda x: f"${x:,.1f}B")
    
    # 繪製表格
    table = ax.table(cellText=display_df.values,
                     colLabels=display_df.columns,
                     rowLabels=display_df.index.strftime('%Y-%m-%d'),
                     cellLoc='center',
                     loc='center')
    
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    table.scale(1.2, 1.2) # 調整表格大小
    
    plt.title("Fed Liquidity Monitor (Last 5 Weeks)", fontweight="bold")
    plt.savefig(filename, bbox_inches='tight', dpi=150)
    plt.close()
    print(f"✅ 流動性表格已存為 {filename}")
    return filename

if __name__ == "__main__":
    df = get_liquidity_monitor()
    analyze_changes(df)
