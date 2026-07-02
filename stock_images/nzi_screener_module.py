#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
N字反包选股模块 - 集成到每日复盘脚本
依赖 daily_stock_screener.py 中的已有函数：
  get_zt_pool, get_batch_realtime, get_stock_kline, is_main_board, filter_st, HEADERS
不修改原有三类选股代码，仅新增第四类
"""

import requests
import time
from datetime import datetime, timedelta, timezone

# ========== N字反包专用配置 ==========

# 热门概念板块映射
HOT_SECTORS_NZI = {
    "化工/氟化工": ["化学制品", "化学原料", "农化制品", "塑料", "橡胶", "非金属材料"],
    "创新药/医药": ["化学制药", "生物制品", "医疗服务", "医疗器械", "中药", "医药商业"],
    "机器人/汽零": ["汽车零部", "自动化设备", "通用设备", "专用设备", "电机", "金属新材"],
    "消费电子/光刻胶": ["消费电子", "光学光电", "元件", "半导体", "其他电子"],
    "通信/算力": ["通信设备", "IT服务", "软件开发", "计算机设备"],
    "电网/电力": ["电网设备", "电力", "其他电源", "风电设备", "光伏设备"],
    "有色/资源": ["贵金属", "工业金属", "小金属", "能源金属", "冶炼"],
    "家电/家居": ["家电零部", "白色家电", "家居用品"],
    "军工": ["航空装备", "军工电子", "航天装备"],
    "物流": ["物流"],
    "食品饮料": ["非白酒", "饮料乳品", "食品加工", "化妆品"],
}


def get_realtime_detail(codes):
    """
    批量获取实时行情（含PE、成交额）
    腾讯API的parts[39]为PE，parts[37]为成交额(万元)，parts[38]为换手率
    返回: dict {code: {name, price, change_pct, pe, amount_yi, turnover_rate}}
    """
    if not codes:
        return {}
    tc_list = [f'sh{c}' if c.startswith('6') else f'sz{c}' for c in codes]
    result = {}
    batch_size = 50
    for i in range(0, len(tc_list), batch_size):
        batch = tc_list[i:i + batch_size]
        url = "https://qt.gtimg.cn/q=" + ",".join(batch)
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            for line in resp.text.strip().split("\n"):
                if "=" not in line:
                    continue
                val = line.split("=", 1)[1].strip().strip('"').strip(";")
                parts = val.split("~")
                if len(parts) >= 39:
                    code = parts[2]
                    pe = 0
                    try:
                        pe = float(parts[39]) if len(parts) > 39 and parts[39] else 0
                    except (ValueError, TypeError):
                        pe = 0
                    amount_wan = 0
                    try:
                        amount_wan = float(parts[37]) if len(parts) > 37 and parts[37] else 0
                    except (ValueError, TypeError):
                        amount_wan = 0
                    result[code] = {
                        "name": parts[1],
                        "price": float(parts[3]) if parts[3] else 0,
                        "change_pct": float(parts[32]) if len(parts) > 32 and parts[32] else 0,
                        "pe": pe,
                        "amount_yi": amount_wan / 10000,  # 万元→亿元
                        "turnover_rate": float(parts[38]) if len(parts) > 38 and parts[38] else 0,
                    }
            time.sleep(0.3)
        except Exception as e:
            print(f"[N字反包] 行情查询失败: {e}")
    return result


def get_recent_zt_dates(date_str, num_days=4):
    """
    获取最近N个交易日的日期列表（用于回溯涨停板）
    返回: ["20260629", "20260630", ...]
    """
    today = datetime.strptime(date_str, "%Y%m%d")
    dates = []
    checked = 0
    offset = 0
    while len(dates) < num_days and checked < num_days + 10:
        offset += 1
        d = today - timedelta(days=offset)
        # 跳过周末
        if d.weekday() >= 5:
            continue
        dates.append(d.strftime("%Y%m%d"))
        checked += 1
    return dates


def get_zt_pool_with_hybk(date_str):
    """
    获取涨停板数据（含行业板块hybk字段）
    复用已有get_zt_pool但额外获取hybk
    """
    url = "https://push2ex.eastmoney.com/getTopicZTPool"
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": "0",
        "Pagesize": "500",
        "sort": "fbt:asc",
        "date": date_str,
        "_": str(int(time.time() * 1000)),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = resp.json()
        if not data.get("data") or not data["data"].get("pool"):
            return []
        result = []
        for item in data["data"]["pool"]:
            name = item.get("n", "")
            if "ST" in name:
                continue
            code = item.get("c", "")
            lbc = item.get("lbc", 0)
            if isinstance(lbc, str):
                try:
                    lbc = int(lbc)
                except:
                    lbc = 0
            result.append({
                "code": code,
                "name": name,
                "lbc": lbc,
                "hybk": item.get("hybk", ""),
                "fund": item.get("fund", 0),
                "hs": item.get("hs", 0),
            })
        return result
    except Exception as e:
        print(f"[N字反包] 获取{date_str}涨停板失败: {e}")
        return []


def run_nzi_filter(date_str, max_count=20):
    """
    N字反包选股（V2逻辑）
    
    筛选条件：
    1. 主板（60/00开头）
    2. 近4天有涨停，今天断板（不涨停）
    3. 断板≥2天
    4. 上升趋势：MA5 > MA10 > MA20
    5. 缩量企稳MA5（±5%）
    6. 不破MA10（最低价≥MA10×98%）
    7. 断板不大跌（最大跌>-12%，今天>-5%）
    8. 热门概念匹配
    
    评分体系（满分30分）：
    - 技术面15分：断板天数3 + MA5贴合3 + 缩量3 + 连板2 + 不大跌2 + 站MA10 1 + 趋势1
    - PE估值4分：≤20=4, ≤40=3, ≤80=2, ≤150=1
    - 人气热度5分：成交额0-3 + 换手率0-2
    - 板块热度3分：同板块涨停≥5=3, ≥3=2, ≥2=1
    - 上升强度3分：MA5-MA10>1%=1, MA10-MA20>1%=1, ... (实际是趋势1+上升1+上升1=3)
    
    返回: list[dict]，每个dict包含 name, code, score, hot_cat, ...（兼容create_stock_image）
    """
    print("\n[N字反包] 开始筛选...")
    
    # 获取最近4个交易日日期
    recent_dates = get_recent_zt_dates(date_str, num_days=4)
    print(f"[N字反包] 回溯日期: {recent_dates}")
    
    # 获取4天涨停板数据，建立候选池
    all_zt = {}  # code -> {name, zt_dates, lbc_max, hybk}
    sector_zt_count = {}  # hybk -> 涨停股数量
    
    for d in recent_dates:
        pool = get_zt_pool_with_hybk(d)
        print(f"[N字反包] {d}: {len(pool)} 只涨停")
        for item in pool:
            code = item["code"]
            hybk = item.get("hybk", "")
            if code not in all_zt:
                all_zt[code] = {
                    "name": item["name"],
                    "zt_dates": [d],
                    "lbc_max": item["lbc"],
                    "hybk": hybk,
                }
            else:
                all_zt[code]["zt_dates"].append(d)
                all_zt[code]["lbc_max"] = max(all_zt[code]["lbc_max"], item["lbc"])
            
            # 统计板块涨停数
            if hybk:
                sector_zt_count[hybk] = sector_zt_count.get(hybk, 0) + 1
        
        time.sleep(0.5)
    
    # 今天的涨停股集合（用于排除今天还涨停的）
    today_pool = get_zt_pool_with_hybk(date_str)
    today_zt_codes = set(item["code"] for item in today_pool)
    
    # 筛选断板候选：之前有涨停，今天不涨停
    candidates = []
    for code, info in all_zt.items():
        if code in today_zt_codes:
            continue  # 今天还涨停，不是断板
        if not is_main_board(code):
            continue
        candidates.append({
            "code": code,
            "name": info["name"],
            "hybk": info["hybk"],
            "zt_dates": info["zt_dates"],
            "lbc_max": info["lbc_max"],
        })
    
    print(f"[N字反包] 断板候选: {len(candidates)} 只（主板+之前涨停+今天断板）")
    
    # 逐只验证K线
    qualified = []
    
    for c in candidates:
        code = c["code"]
        klines = get_stock_kline(code, days=30)
        if not klines or len(klines) < 20:
            continue
        
        closes = [k["close"] for k in klines]
        vols = [k["volume"] for k in klines]
        lows = [k["low"] for k in klines]
        
        # 找最近涨停日
        zt_idx = -1
        for i in range(len(klines) - 1, 0, -1):
            chg = (closes[i] - closes[i-1]) / closes[i-1] * 100
            if chg >= 9.8:
                zt_idx = i
                break
        if zt_idx == -1:
            continue
        
        # 连板数
        lianban = 0
        for i in range(zt_idx, 0, -1):
            chg = (closes[i] - closes[i-1]) / closes[i-1] * 100
            if chg >= 9.8:
                lianban += 1
            else:
                break
        
        # 断板≥2天
        days_after = len(klines) - 1 - zt_idx
        if days_after < 2:
            continue
        
        # MA计算
        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20
        
        # 上升趋势
        if not (ma5 > ma10 > ma20):
            continue
        
        # MA5企稳±5%
        price = closes[-1]
        ma5_diff = (price - ma5) / ma5 * 100
        if abs(ma5_diff) > 5:
            continue
        
        # 不破MA10
        if lows[-1] < ma10 * 0.98:
            continue
        
        # 缩量
        vol_recent_3 = sum(vols[-3:]) / 3
        vol_zt = vols[zt_idx]
        vol_ratio = vol_recent_3 / vol_zt if vol_zt > 0 else 1
        if vol_ratio > 1.3:
            continue
        
        # 断板不大跌
        max_drop = 0
        for i in range(zt_idx + 1, len(klines)):
            drop = (closes[i] - closes[zt_idx]) / closes[zt_idx] * 100
            max_drop = min(max_drop, drop)
        if max_drop < -12:
            continue
        
        today_chg = (closes[-1] - closes[-2]) / closes[-2] * 100
        if today_chg < -5:
            continue
        
        # 热门概念匹配
        sector = c["hybk"] or ""
        hot_cat = ""
        for cat, keywords in HOT_SECTORS_NZI.items():
            for kw in keywords:
                if kw in sector:
                    hot_cat = cat
                    break
            if hot_cat:
                break
        if not hot_cat:
            continue
        
        # 获取实时行情（含PE、成交额）
        rt_data = get_realtime_detail([code])
        r = rt_data.get(code, {})
        pe = r.get("pe", 0)
        amount = r.get("amount_yi", 0)  # 已转为亿
        turnover = r.get("turnover_rate", 0)
        
        # ============ 评分（满分30分）============
        score = 0
        
        # 1. 断板天数 (0-3)
        if 2 <= days_after <= 4:
            score += 3
        elif days_after >= 5:
            score += 1
        
        # 2. MA5贴合度 (0-3)
        if abs(ma5_diff) <= 3:
            score += 3
        elif abs(ma5_diff) <= 5:
            score += 1
        
        # 3. 缩量程度 (0-3)
        if vol_ratio < 0.7:
            score += 3
        elif vol_ratio < 1.0:
            score += 2
        elif vol_ratio < 1.2:
            score += 1
        
        # 4. 连板数 (0-2)
        if lianban >= 2:
            score += 2
        
        # 5. 断板不大跌 (0-2)
        if max_drop > -5:
            score += 2
        elif max_drop > -8:
            score += 1
        
        # 6. 站上MA10 (0-1)
        if price > ma10:
            score += 1
        
        # 7. 上升趋势强度 (0-1)
        ma5_ma10_gap = (ma5 - ma10) / ma10 * 100
        if ma5_ma10_gap > 1:
            score += 1
        
        # 8. PE估值 (0-4)
        if pe > 0:
            if pe <= 20:
                score += 4
            elif pe <= 40:
                score += 3
            elif pe <= 80:
                score += 2
            elif pe <= 150:
                score += 1
        
        # 9. 人气热度 (0-5)
        if amount >= 30:
            score += 3
        elif amount >= 10:
            score += 2
        elif amount >= 5:
            score += 1
        if 3 <= turnover <= 15:
            score += 2
        elif 1 <= turnover < 3 or 15 < turnover <= 20:
            score += 1
        
        # 10. 板块热度 (0-3)
        same_sector = sector_zt_count.get(sector, 0)
        if same_sector >= 5:
            score += 3
        elif same_sector >= 3:
            score += 2
        elif same_sector >= 2:
            score += 1
        
        qualified.append({
            "name": c["name"],
            "code": code,
            "score": score,
            "hot_cat": hot_cat,
            "pe": pe,
            "price": r.get("price", price),
            "amount": amount,
            "turnover": turnover,
            "lianban": lianban,
            "days_after": days_after,
            "ma5": ma5,
            "ma10": ma10,
            "ma20": ma20,
            "vol_ratio": vol_ratio,
            "today_chg": r.get("change_pct", today_chg),
        })
        
        time.sleep(0.1)
    
    # 按评分降序排序
    qualified.sort(key=lambda x: -x["score"])
    result = qualified[:max_count]
    
    print(f"[N字反包] 符合条件: {len(qualified)} 只，取前{len(result)}只")
    for i, s in enumerate(result, 1):
        print(f"  {i:02d}. {s['name']}({s['code']}) [{s['hot_cat']}] 评分:{s['score']}/30 PE:{s['pe']:.0f}")
    
    return result


# ========== 集成到主流程的方法 ==========
# 在 daily_stock_screener.py 的 main() 函数中，在生成断板股图片之后添加：
#
#   # ===== Step 5.6: N字反包选股 =====
#   print("\n[Step 5.6] N字反包选股...")
#   from nzi_screener_module import run_nzi_filter
#   nzi_stocks = run_nzi_filter(date_str)
#   nzi_img = create_stock_image("N字反包", nzi_stocks, f"{output_dir}/N字反包_{date_str}.png", date_display)
#   send_image(nzi_img)
#
# 或直接将 run_nzi_filter 和相关函数复制到 daily_stock_screener.py 中


# ========== 独立测试入口 ==========
if __name__ == "__main__":
    # 使用已有的HEADERS和工具函数
    import sys
    sys.path.insert(0, "/workspace/stock_images")
    
    # 导入依赖
    from daily_stock_screener import (
        HEADERS, get_batch_realtime, get_stock_kline, 
        is_main_board, filter_st, create_stock_image
    )
    
    from datetime import timezone, timedelta
    
    beijing_now = datetime.now(timezone(timedelta(hours=8)))
    date_str = beijing_now.strftime("%Y%m%d")
    date_display = beijing_now.strftime("%Y.%m.%d")
    
    print(f"=== N字反包选股测试 ===")
    print(f"日期: {date_display}")
    
    # 运行筛选
    nzi_stocks = run_nzi_filter(date_str)
    
    # 用与三类选股相同的create_stock_image生成图片
    output_dir = "/workspace/stock_images"
    nzi_img = create_stock_image("N字反包", nzi_stocks, f"{output_dir}/N字反包_{date_str}.png", date_display)
    
    print(f"\n图片已生成: {nzi_img}")
    print(f"共 {len(nzi_stocks)} 只标的")
