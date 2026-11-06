"""
量化燈號模型 (Python 決定燈號，Gemini 只負責解讀)

每個因子給 -2 ~ +2 分，總分決定燈號：
    總分 >= +3  → 🟢 綠燈
    總分 <= -3  → 🔴 紅燈
    其他        → 🟡 黃燈
情緒指標 (AAII / CNN) 屬逆向指標，不計分，只作為「極端情緒」註記。
"""
import re


def _vix_score(vix):
    if vix is None: return 0, "無資料"
    if vix < 15: return 1, f"{vix:.1f} 低波動"
    if vix < 20: return 0, f"{vix:.1f} 正常"
    if vix < 25: return -1, f"{vix:.1f} 偏高"
    return -2, f"{vix:.1f} 恐慌"


def _trend_score(bias, spy_chg):
    if bias is None: return 0, "無資料"
    score = 1 if bias > 0 else -1
    note = f"SPY 距 20MA {bias:+.1f}%"
    if spy_chg is not None and spy_chg <= -2:
        score -= 1
        note += f"，單日 {spy_chg:+.1f}%"
    return max(-2, min(2, score)), note


def _breadth_score(chg):
    if chg is None: return 0, "無資料"
    if chg > 1: return 1, f"RSP/SPY 20日 {chg:+.1f}% (擴散)"
    if chg < -1: return -1, f"RSP/SPY 20日 {chg:+.1f}% (集中)"
    return 0, f"RSP/SPY 20日 {chg:+.1f}% (持平)"


def _sentiment_note(aaii_display, cnn_score):
    spread = None
    m = re.search(r"Spread:([+-]?\d+(?:\.\d+)?)%", aaii_display or "")
    if m: spread = float(m.group(1))
    fear = (cnn_score is not None and cnn_score < 25) or (spread is not None and spread < -15)
    greed = (cnn_score is not None and cnn_score > 75) or (spread is not None and spread > 25)
    if fear and greed: return "情緒訊號分歧"
    if fear: return "極度恐懼 (逆向觀察：短期可能接近超賣，但需等趨勢確認，不單獨構成買點)"
    if greed: return "極度貪婪 (逆向觀察：追高風險升高)"
    return "情緒中性"


def compute_regime(m_data, liq_sig=None, risk_app=None):
    factors = []  # (名稱, 分數, 說明)

    factors.append(("波動 (VIX)", *_vix_score(m_data.get('vix'))))
    factors.append(("趨勢 (SPY)", *_trend_score(m_data.get('bias'), m_data.get('spy_chg'))))

    if liq_sig:
        factors.append(("流動性 (4週)", liq_sig['score'],
                        f"{liq_sig['label']} 4週 {liq_sig['chg_4w']:+,.0f}B / 1週 {liq_sig['chg_1w']:+,.0f}B"))
    else:
        factors.append(("流動性 (4週)", 0, "無資料"))

    if risk_app:
        tag = "風險偏好" if risk_app['spread'] > 0 else "避險"
        factors.append(("板塊輪動 (20日)", risk_app['score'],
                        f"進攻-防禦 {risk_app['spread']:+.1f}% ({tag})"))
    else:
        factors.append(("板塊輪動 (20日)", 0, "無資料"))

    factors.append(("市場廣度", *_breadth_score(m_data.get('breadth_chg_20d'))))

    total = sum(f[1] for f in factors)
    if total >= 3: light = "🟢"; label = "綠燈"
    elif total <= -3: light = "🔴"; label = "紅燈"
    else: light = "🟡"; label = "黃燈"

    sentiment = _sentiment_note(m_data.get('aaii_display'), m_data.get('cnn_score'))
    return {'light': light, 'label': label, 'total': total, 'factors': factors,
            'sentiment': sentiment}


def format_regime(r):
    lines = [f"量化燈號: {r['light']} {r['label']} (總分 {r['total']:+d}，範圍 -9 ~ +7；≥+3 綠，≤-3 紅)"]
    for name, score, note in r['factors']:
        lines.append(f"  {name:<12} {score:+d}  {note}")
    lines.append(f"  情緒註記      {r['sentiment']}")
    return "\n".join(lines)
