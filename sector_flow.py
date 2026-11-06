import yfinance as yf
import pandas as pd
import numpy as np

# ==========================================
# 1. 設定：全球國家 ETF (New)
# ==========================================
COUNTRY_MAP = {
    'QQQ': '美國那指', # 科技成長
    'IWM': '美國羅素', # 小型股
    'EEM': '新興市場',
    'EFA': '先進市場',
    'EWT': '台灣',
    'MCHI': '中國',
    'EWJ': '日本',
    'INDA': '印度',
    'EWG': '德國',
    'EWU': '英國',
    'EWC': '加拿大',
    'EWA': '澳洲',
    'EWZ': '巴西',
    'VNM': '越南',
    'EWY': '南韓'
}

# ==========================================
# 2. 設定：美股板塊與細分產業 (Existing)
# ==========================================
SECTOR_MAP = {
    'XLE': {'name': '能源', 'subs': ['XOP', 'OIH', 'IEO', 'FCG', 'CRAK']},
    'XLC': {'name': '通訊', 'subs': ['SOCL', 'VOX', 'NXTG']},
    'XLU': {'name': '公用', 'subs': ['IDU', 'VPU', 'FUTY', 'JXI']},
    'XLI': {'name': '工業', 'subs': ['ITA', 'JETS', 'IYT', 'IYJ', 'PHO', 'XTN']},
    'XLP': {'name': '必消', 'subs': ['PBJ', 'KXI', 'IYK']}, 
    'XLF': {'name': '金融', 'subs': ['KRE', 'KBE', 'IAI', 'IYF', 'FNCL', 'KBWB']},
    'XLRE': {'name': '房產', 'subs': ['REZ', 'REM', 'INDS', 'PPTY']},
    'XLK': {'name': '科技', 'subs': ['SMH', 'IGV', 'CIBR', 'SKYY', 'AIQ', 'SOXX', 'FTEC']},
    'XLB': {'name': '原物料', 'subs': ['GDX', 'GDXJ', 'SIL', 'LIT', 'URA', 'MOO', 'COPX']},
    'XLY': {'name': '非必消', 'subs': ['XRT', 'XHB', 'PEJ', 'BETZ', 'ITB', 'CHIQ']},
    'XLV': {'name': '醫療', 'subs': ['XBI', 'IBB', 'IHI', 'IHE', 'PJP', 'FBT']}
}

SUB_NAME_MAP = {
    'SMH': '半導體', 'IGV': '軟體', 'CIBR': '資安', 'SKYY': '雲端', 'AIQ': '人工智慧', 'SOXX': '費半', 'FTEC': '科技指',
    'KRE': '區域銀', 'KBE': '銀行', 'IAI': '經紀商', 'IYF': '金融', 'FNCL': '金融科', 'KBWB': '大型銀',
    'XBI': '生技XBI', 'IBB': '生技指', 'IHI': '醫材', 'IHE': '製藥IHE', 'PJP': '製藥PJP', 'FBT': '生技FBT',
    'XRT': '零售', 'XHB': '營建', 'PEJ': '休閒', 'BETZ': '博弈', 'ITB': '營建指', 'CHIQ': '非消指',
    'PBJ': '食品', 'KXI': '必需', 'IYK': '必需指',
    'XOP': '油氣探', 'OIH': '油氣服', 'CRAK': '煉油', 'FCG': '天然氣', 'IEO': '能源指',
    'ITA': '航太', 'JETS': '航空', 'IYT': '運輸', 'IYJ': '工業指', 'PHO': '水資源', 'XTN': '運輸指',
    'GDX': '金礦', 'GDXJ': '小金礦', 'SIL': '白銀', 'LIT': '鋰電', 'URA': '鈾礦', 'MOO': '農業', 'COPX': '銅礦',
    'IDU': '公用', 'VPU': '公用VPU', 'FUTY': '公用FUTY', 'JXI': '全球公用',
    'REZ': '住宅', 'REM': '抵押產', 'INDS': '工業產', 'PPTY': '地產',
    'SOCL': '社群', 'VOX': '通訊指', 'NXTG': '次代網'
}

def get_name(ticker):
    if ticker in COUNTRY_MAP: return COUNTRY_MAP[ticker] # Check Country first
    if ticker in SECTOR_MAP: return SECTOR_MAP[ticker]['name']
    return SUB_NAME_MAP.get(ticker, ticker)

def download_and_process_data():
    # 準備所有 Tickers (Country + Sector + Sub + SPY)
    country_tickers = list(COUNTRY_MAP.keys())
    major_tickers = list(SECTOR_MAP.keys())
    sub_tickers = [item for sublist in [v['subs'] for v in SECTOR_MAP.values()] for item in sublist]
    all_tickers = list(set(country_tickers + major_tickers + sub_tickers + ['SPY']))

    print("正在下載全市場數據 (含各國 ETF)...")
    
    try:
        data = yf.download(all_tickers, period="2y", progress=False, auto_adjust=False)
        
        # 處理資料結構
        if isinstance(data.columns, pd.MultiIndex):
            if 'Adj Close' in data.columns.get_level_values(0):
                data = data['Adj Close']
            else:
                data = data['Close']
        elif 'Adj Close' in data.columns:
            data = data['Adj Close']
            
    except Exception as e:
        print(f"數據下載錯誤: {e}")
        return None

    # 重試下載失敗的代號 (yfinance 多執行緒偶爾出現 'database is locked')
    missing = [t for t in all_tickers if t not in data.columns or data[t].isna().all()]
    if missing:
        print(f"重試下載: {missing}")
        try:
            retry = yf.download(missing, period="2y", progress=False, auto_adjust=False, threads=False)
            col = 'Adj Close' if 'Adj Close' in retry.columns.get_level_values(0) else 'Close'
            retry = retry[col]
            if isinstance(retry, pd.Series):
                retry = retry.to_frame(missing[0])
            for t in retry.columns:
                if not retry[t].isna().all():
                    data[t] = retry[t]
        except Exception as e:
            print(f"重試失敗: {e}")

    # 個別 ETF 偶爾缺最新一筆報價：最多往前補 3 天，避免出現 nan
    data = data.sort_index().ffill(limit=3)

    # 資料品質檢查：ETF 單日漲跌超過 ±20% 幾乎都是分割/資料錯誤，排除該代號
    # 只檢查計算 200 日 RS 會用到的區間
    daily = data.tail(205).pct_change(fill_method=None)
    bad = [t for t in daily.columns if (daily[t].abs() > 0.20).any()]
    if bad:
        print(f"⚠️ 資料異常 (單日變動 >20%，疑似分割或錯誤)，已排除: {bad}")
        data = data.drop(columns=bad)
    return data

def calculate_rankings(data):
    if data is None: return None
    
    periods = [5, 20, 60, 200]
    final_output = {} 

    for days in periods:
        if len(data) < days: continue
        
        pct_change = data.pct_change(days, fill_method=None).iloc[-1]
        
        if 'SPY' not in pct_change: continue
        spy_ret = pct_change['SPY']
        
        # RS = Ticker% - SPY%
        rs_series = ((pct_change - spy_ret) * 100).dropna()
        
        # --- 1. 全球國家排名 (Country) ---
        country_tickers = list(COUNTRY_MAP.keys())
        valid_countries = [t for t in country_tickers if t in rs_series.index]
        country_ranked = rs_series[valid_countries].sort_values(ascending=False)

        # --- 2. 美股大板塊排名 (Major Sector) ---
        major_tickers = list(SECTOR_MAP.keys())
        valid_majors = [t for t in major_tickers if t in rs_series.index]
        major_ranked = rs_series[valid_majors].sort_values(ascending=False)
        
        top_4_majors = major_ranked.head(4).index.tolist()
        
        # --- 3. 細分產業排名 (Sub Sector - Top 4 Only) ---
        target_subs = []
        for m in top_4_majors:
            target_subs.extend(SECTOR_MAP[m]['subs'])
            
        valid_subs = [t for t in target_subs if t in rs_series.index]
        sub_ranked = rs_series[valid_subs].sort_values(ascending=False)
        
        final_output[days] = {
            'country': country_ranked,
            'major': major_ranked,
            'sub': sub_ranked,
            'top_4_names': [SECTOR_MAP[t]['name'] for t in top_4_majors]
        }
        
    return final_output

# 進攻型 vs 防禦型板塊
OFFENSE = ['XLK', 'XLY', 'XLC']
DEFENSE = ['XLP', 'XLV', 'XLU']

def risk_appetite(final_output, days=20):
    """進攻板塊平均 RS - 防禦板塊平均 RS。正值 = 風險偏好，負值 = 避險。"""
    if not final_output or days not in final_output:
        return None
    major = final_output[days]['major']
    off = [major[t] for t in OFFENSE if t in major.index]
    dfn = [major[t] for t in DEFENSE if t in major.index]
    if not off or not dfn:
        return None
    spread = sum(off) / len(off) - sum(dfn) / len(dfn)
    if spread > 8: score = 2
    elif spread > 3: score = 1
    elif spread < -8: score = -2
    elif spread < -3: score = -1
    else: score = 0
    return {'spread': spread, 'score': score, 'days': days}

def print_aligned_table(final_output):
    if not final_output: return

    periods = [5, 20, 60, 200]
    col_width = 18
    header_str = "    " + "".join([f"{p} 日 RS".ljust(col_width) for p in periods])
    
    # ==========================================
    # Table 0: Global Country Flows
    # ==========================================
    print("\n" + "="*80)
    print("🌍 全球資金流向 (相對於美股 SPY)")
    print("="*80)
    print(header_str)
    
    # 顯示所有設定的國家 (數量固定)
    for i in range(len(COUNTRY_MAP)):
        row_str = f"{i+1:<4}"
        for days in periods:
            if days in final_output and i < len(final_output[days]['country']):
                item = final_output[days]['country'].iloc[i]
                ticker = final_output[days]['country'].index[i]
                name = get_name(ticker)
                cell = f"{name} ({item:+.1f}%)"
                row_str += f"{cell:<18}"
            else:
                row_str += "".ljust(col_width)
        print(row_str)

    # ==========================================
    # Table 1: Major Sectors
    # ==========================================
    print("\n" + "="*80)
    print("🇺🇸 美股 11 大板塊資金流向")
    print("="*80)
    print(header_str)
    
    for i in range(11):
        row_str = f"{i+1:<4}"
        for days in periods:
            if days in final_output and i < len(final_output[days]['major']):
                item = final_output[days]['major'].iloc[i]
                ticker = final_output[days]['major'].index[i]
                name = get_name(ticker)
                cell = f"{name} ({item:+.1f}%)"
                row_str += f"{cell:<18}" 
            else:
                row_str += "".ljust(col_width)
        print(row_str)

    # 顯示 Top 4 摘要
    print("\n" + "="*80)
    print("各週期最強勢的 4 大板塊 (決定下方細分產業的篩選範圍):")
    for days in periods:
        if days in final_output:
            names = ",".join(final_output[days]['top_4_names'])
            print(f"[{days}日]: {names}")
    print("="*80)

    # ==========================================
    # Table 2: Sub Sectors
    # ==========================================
    print("🔥 強勢細分產業 (Top 4 板塊旗下所有子項目)")
    print("="*80)
    print(header_str)
    
    max_rows = 0
    for days in periods:
        if days in final_output:
            max_rows = max(max_rows, len(final_output[days]['sub']))
            
    for i in range(max_rows):
        row_str = f"{i+1:<4}"
        for days in periods:
            if days in final_output and i < len(final_output[days]['sub']):
                item = final_output[days]['sub'].iloc[i]
                ticker = final_output[days]['sub'].index[i]
                name = get_name(ticker)
                cell = f"{name} ({item:+.1f}%)"
                row_str += f"{cell:<18}"
            else:
                row_str += "".ljust(col_width)
        print(row_str)
    print("="*80)
    for d in (5, 20):
        ra = risk_appetite(final_output, d)
        if ra:
            tag = "風險偏好" if ra['spread'] > 0 else "避險"
            print(f"⚖️ 進攻(科技/非必消/通訊) vs 防禦(必消/醫療/公用) {d}日: {ra['spread']:+.1f}% → {tag}")
    print("="*80)

if __name__ == "__main__":
    data = download_and_process_data()
    rankings = calculate_rankings(data)
    print_aligned_table(rankings)
