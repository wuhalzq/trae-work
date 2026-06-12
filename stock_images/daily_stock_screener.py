#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A股每日筛选自动化脚本（真实数据版）
数据来源：
  1. 复盘网（fupanwang.com）- 人气排行榜
  2. 东方财富 - 涨停板数据
  3. 东方财富 - A股实时行情
  4. 东方财富 - 个股历史K线

功能：
  1. 获取当日A股数据（人气榜、涨停榜、历史行情）
  2. 执行三个筛选条件（连板/回调/断板）
  3. 生成精简版图片
  4. 通过企业微信推送结果
"""

import json
import base64
import hashlib
import re
import time
import requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont

# ========== 配置 ==========
WEBHOOK_KEY = "c62953cf-031b-4d0e-a99f-513593e55771"
WEBHOOK_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/",
    "Accept": "application/json, text/plain, */*",
}

# ========== 交易日判断 ==========

def get_beijing_now():
    """获取北京时间"""
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=8)))

def is_trading_day():
    """判断是否为交易日（排除周末，基于北京时间）"""
    today = get_beijing_now()
    return today.weekday() < 5

# ========== 数据获取：复盘网人气榜 ==========

def get_renqi_data():
    """
    从复盘网获取人气排行榜数据
    返回: list[dict]，每个dict包含 code, name, mark, rank, change_pct
    """
    url = "https://adm.fupanwang.com/renqi"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.encoding = "utf-8"
    except Exception as e:
        print(f"[人气榜] 请求失败: {e}")
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    table = soup.select_one("table")
    if not table:
        print("[人气榜] 未找到表格")
        return []
    
    tbody = table.find("tbody")
    if not tbody:
        tbody = table  # 有些页面没有tbody
    rows = tbody.find_all("tr")
    
    result = []
    for row in rows:
        tds = row.find_all("td")
        if len(tds) < 6:
            continue
        
        # 序号
        idx_text = tds[0].get_text(strip=True)
        try:
            idx = int(idx_text)
        except ValueError:
            continue
        
        # 股票名称和代码
        name_link = tds[1].find("a")
        if name_link:
            stock_name = name_link.get_text(strip=True)
            # 从tooltip或href中提取代码
            tooltip = name_link.get("tooltip", "")
            href = name_link.get("href", "")
            stock_code = ""
            if tooltip:
                stock_code = tooltip
            elif href:
                code_match = re.search(r'/(\d{6})\.', href)
                if code_match:
                    stock_code = code_match.group(1)
        else:
            stock_name = tds[1].get_text(strip=True)
            stock_code = ""
        
        # 跳过VIP锁定的
        if stock_name == "点击解锁" or not stock_code:
            continue
        
        # 标记（连板信息）
        mark = tds[2].get_text(strip=True) if len(tds) > 2 else ""
        mark = re.sub(r'\s+', '', mark)
        
        # 涨幅
        change_text = tds[5].get_text(strip=True) if len(tds) > 5 else "0%"
        change_match = re.search(r'([-\d.]+)%', change_text)
        change_pct = float(change_match.group(1)) if change_match else 0.0
        
        result.append({
            "code": stock_code,
            "name": stock_name,
            "mark": mark,
            "rank": idx,
            "change_pct": change_pct,
        })
    
    print(f"[人气榜] 获取到 {len(result)} 条数据")
    return result

# ========== 数据获取：东方财富涨停板 ==========

def get_zt_pool(date_str):
    """
    从东方财富获取涨停板数据
    返回: list[dict]，每个dict包含 code, name, change_pct, fund, lbc(连板数), hs
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
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = response.json()
    except Exception as e:
        print(f"[涨停板] 请求失败: {e}")
        return []
    
    if not data.get("data") or not data["data"].get("pool"):
        print(f"[涨停板] 日期 {date_str} 无涨停数据")
        return []
    
    result = []
    for item in data["data"]["pool"]:
        code = item.get("c", "")
        name = item.get("n", "")
        
        # 跳过ST股
        if "ST" in name:
            continue
        
        # 解析连板天数
        lbc = item.get("lbc", 0)
        if isinstance(lbc, str):
            try:
                lbc = int(lbc)
            except ValueError:
                lbc = 0
        
        result.append({
            "code": code,
            "name": name,
            "change_pct": item.get("zf", 0),
            "fund": item.get("fund", 0),  # 封单金额
            "lbc": lbc,  # 连板天数
            "hs": item.get("hs", 0),  # 换手率
        })
    
    print(f"[涨停板] 获取到 {len(result)} 只非ST涨停股")
    return result

# ========== 数据获取：东方财富昨日涨停板 ==========

def get_yesterday_zt_pool(date_str):
    """获取昨日涨停板数据（用于断板筛选）"""
    # date_str是今天，昨天需要计算
    today = datetime.strptime(date_str, "%Y%m%d")
    # 简单回退1天（非交易日可能需要回退更多，这里先回退1天）
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y%m%d")
    
    url = "https://push2ex.eastmoney.com/getTopicZTPool"
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": "0",
        "Pagesize": "500",
        "sort": "fbt:asc",
        "date": yesterday_str,
        "_": str(int(time.time() * 1000)),
    }
    
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        data = response.json()
    except Exception as e:
        print(f"[昨日涨停] 请求失败: {e}")
        return []
    
    if not data.get("data") or not data["data"].get("pool"):
        # 如果昨天没有数据（周末），继续回退
        for offset in range(2, 7):
            prev = today - timedelta(days=offset)
            prev_str = prev.strftime("%Y%m%d")
            params["date"] = prev_str
            try:
                response = requests.get(url, params=params, headers=HEADERS, timeout=15)
                data = response.json()
                if data.get("data") and data["data"].get("pool"):
                    break
            except Exception:
                continue
        else:
            print(f"[昨日涨停] 未找到近期涨停数据")
            return []
    
    result = []
    for item in data["data"]["pool"]:
        code = item.get("c", "")
        name = item.get("n", "")
        if "ST" in name:
            continue
        lbc = item.get("lbc", 0)
        if isinstance(lbc, str):
            try:
                lbc = int(lbc)
            except ValueError:
                lbc = 0
        result.append({
            "code": code,
            "name": name,
            "lbc": lbc,
        })
    
    print(f"[昨日涨停] 获取到 {len(result)} 只非ST涨停股")
    return result

# ========== 数据获取：个股历史K线 ==========

def get_stock_kline(stock_code, days=20):
    """
    获取个股近N日日K线数据
    返回: list[dict]，每条包含 date, close, high, low, change_pct, volume, amount
    """
    market = "1" if stock_code.startswith("6") else "0"
    secid = f"{market}.{stock_code}"
    
    url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
    params = {
        "secid": secid,
        "klt": "101",  # 日线
        "fqt": "1",    # 前复权
        "beg": "0",
        "end": "20500101",
        "lmt": str(days),
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b",
        "forcect": "1",
        "iscca": "1",
    }
    
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = response.json()
    except Exception as e:
        return []
    
    if not data.get("data") or not data["data"].get("klines"):
        return []
    
    result = []
    for line in data["data"]["klines"]:
        parts = line.split(",")
        if len(parts) >= 9:
            result.append({
                "date": parts[0],
                "open": float(parts[1]),
                "close": float(parts[2]),
                "high": float(parts[3]),
                "low": float(parts[4]),
                "volume": float(parts[5]),
                "amount": float(parts[6]),
                "amplitude": float(parts[7]),
                "change_pct": float(parts[8]),
            })
    
    return result

def check_near_high(stock_code, days=10):
    """
    检查近N日内是否接近近期高点
    判断标准：近N日最高价 >= 近20日最高价的90%
    """
    klines = get_stock_kline(stock_code, days=20)
    if len(klines) < 2:
        return False
    
    # 近20日最高价
    max_high_20 = max(k["high"] for k in klines)
    if max_high_20 <= 0:
        return False
    
    # 近N日最高价
    recent_klines = klines[-days:] if len(klines) >= days else klines
    max_high_recent = max(k["high"] for k in recent_klines)
    
    return max_high_recent >= max_high_20 * 0.9

def check_had_zt_in_days(stock_code, days=20):
    """检查近N日内是否有涨停（涨幅>=9.8%）"""
    klines = get_stock_kline(stock_code, days=days)
    for k in klines:
        if k["change_pct"] >= 9.8:
            return True
    return False

def check_volume_expand(stock_code):
    """检查今日成交额是否放大（对比前5日均量）"""
    klines = get_stock_kline(stock_code, days=10)
    if len(klines) < 6:
        return True  # 数据不足，默认通过
    
    today_amount = klines[-1]["amount"]
    avg_amount = sum(k["amount"] for k in klines[-6:-1]) / 5
    
    if avg_amount <= 0:
        return True
    return today_amount >= avg_amount * 1.2  # 放大20%以上

# ========== 筛选逻辑 ==========

def is_main_board(code):
    """判断是否为主板股票（排除创业板300、科创板688、北交所）"""
    if code.startswith("300") or code.startswith("301"):
        return False  # 创业板
    if code.startswith("688"):
        return False  # 科创板
    if code.startswith("9") or code.startswith("8"):
        return False  # 北交所
    return True

def filter_st(name):
    """判断是否为ST股"""
    return "ST" in name.upper()

def run_filters(renqi_data, zt_today, zt_yesterday):
    """
    执行三个筛选条件
    参数:
      renqi_data: 人气榜数据
      zt_today: 今日涨停股
      zt_yesterday: 昨日涨停股
    返回: dict with lianban, huiluo, duanban
    """
    
    # 构建涨停股代码集合
    zt_today_codes = set(s["code"] for s in zt_today)
    zt_yesterday_codes = set(s["code"] for s in zt_yesterday)
    
    # 构建人气排名映射（代码 -> 排名）
    renqi_rank = {}
    for item in renqi_data:
        renqi_rank[item["code"]] = item["rank"]
    
    # 构建涨停股详细信息映射
    zt_today_map = {s["code"]: s for s in zt_today}
    zt_yesterday_map = {s["code"]: s for s in zt_yesterday}
    
    # ===== 条件1：连板股 =====
    # 今日涨停 + 非ST
    # 优先从人气榜取，不足20则从全部涨停股补充
    lianban = []
    for item in renqi_data:
        code = item["code"]
        name = item["name"]
        
        if code not in zt_today_codes:
            continue
        if filter_st(name):
            continue
        
        zt_info = zt_today_map[code]
        lianban.append({
            "name": name,
            "code": code,
            "change_pct": zt_info.get("change_pct", item.get("change_pct", 0)),
            "lbc": zt_info.get("lbc", 0),
            "mark": item.get("mark", ""),
            "rank": item["rank"],
        })
    
    # 如果人气榜中不足20只，从全部涨停股中补充（按连板数降序）
    if len(lianban) < 20:
        existing_codes = set(s["code"] for s in lianban)
        extra = []
        for s in zt_today:
            if s["code"] in existing_codes:
                continue
            if filter_st(s["name"]):
                continue
            extra.append({
                "name": s["name"],
                "code": s["code"],
                "change_pct": s.get("change_pct", 0),
                "lbc": s.get("lbc", 0),
                "mark": f"{s.get('lbc', 0)}连板" if s.get('lbc', 0) > 1 else "首板",
                "rank": 999,
            })
        extra.sort(key=lambda x: (-x["lbc"], x["code"]))
        lianban.extend(extra[:20 - len(lianban)])
    
    lianban.sort(key=lambda x: x["rank"])
    lianban = lianban[:20]
    print(f"[筛选] 连板股: {len(lianban)} 只")
    
    # ===== 条件2：回调股 =====
    # 今日涨8%以内 + 非ST + 20日内有涨停
    # 放宽：从人气榜取涨8%以内的，不足20则放宽到涨10%以内
    huiluo = []
    checked_codes = set()
    
    # 第一轮：涨8%以内
    for item in renqi_data:
        code = item["code"]
        name = item["name"]
        change_pct = item.get("change_pct", 0)
        
        if change_pct > 8.0:
            continue
        if filter_st(name):
            continue
        
        if code not in checked_codes:
            checked_codes.add(code)
            had_zt = check_had_zt_in_days(code, days=20)
            if not had_zt:
                continue
        
        huiluo.append({
            "name": name,
            "code": code,
            "change_pct": change_pct,
            "mark": item.get("mark", ""),
            "rank": item["rank"],
        })
    
    # 第二轮：如果不足20只，放宽到涨10%以内（即排除涨停股）
    if len(huiluo) < 20:
        for item in renqi_data:
            code = item["code"]
            name = item["name"]
            change_pct = item.get("change_pct", 0)
            
            if change_pct > 10.0 or change_pct <= 8.0:
                continue
            if filter_st(name):
                continue
            if code in checked_codes:
                continue
            
            checked_codes.add(code)
            had_zt = check_had_zt_in_days(code, days=20)
            if not had_zt:
                continue
            
            huiluo.append({
                "name": name,
                "code": code,
                "change_pct": change_pct,
                "mark": item.get("mark", ""),
                "rank": item["rank"],
            })
            if len(huiluo) >= 20:
                break
    
    # 第三轮：如果还不足20只，去掉"20日内有涨停"条件，只取涨8%以内的热门股
    if len(huiluo) < 20:
        for item in renqi_data:
            code = item["code"]
            name = item["name"]
            change_pct = item.get("change_pct", 0)
            
            if change_pct > 8.0:
                continue
            if filter_st(name):
                continue
            if any(h["code"] == code for h in huiluo):
                continue
            
            huiluo.append({
                "name": name,
                "code": code,
                "change_pct": change_pct,
                "mark": item.get("mark", ""),
                "rank": item["rank"],
            })
            if len(huiluo) >= 20:
                break
    
    huiluo.sort(key=lambda x: x["rank"])
    huiluo = huiluo[:20]
    print(f"[筛选] 回调股: {len(huiluo)} 只")
    
    # ===== 条件3：断板股 =====
    # 昨日涨停 + 今日未涨停 + 非ST
    # 优先从人气榜取，不足20则从全部昨日涨停股补充
    duanban = []
    for item in renqi_data:
        code = item["code"]
        name = item["name"]
        
        if code not in zt_yesterday_codes:
            continue
        if code in zt_today_codes:
            continue
        if filter_st(name):
            continue
        
        yt_info = zt_yesterday_map[code]
        duanban.append({
            "name": name,
            "code": code,
            "change_pct": item.get("change_pct", 0),
            "yesterday_lbc": yt_info.get("lbc", 0),
            "mark": item.get("mark", ""),
            "rank": item["rank"],
        })
    
    # 如果人气榜中不足20只，从全部昨日涨停股中补充
    if len(duanban) < 20:
        existing_codes = set(s["code"] for s in duanban)
        extra = []
        for s in zt_yesterday:
            if s["code"] in existing_codes:
                continue
            if s["code"] in zt_today_codes:
                continue
            if filter_st(s["name"]):
                continue
            extra.append({
                "name": s["name"],
                "code": s["code"],
                "change_pct": 0,
                "yesterday_lbc": s.get("lbc", 0),
                "mark": f"昨日{s.get('lbc', 0)}连板" if s.get('lbc', 0) > 1 else "昨日首板",
                "rank": 999,
            })
        extra.sort(key=lambda x: (-x["yesterday_lbc"], x["code"]))
        duanban.extend(extra[:20 - len(duanban)])
    
    duanban.sort(key=lambda x: x["rank"])
    duanban = duanban[:20]
    print(f"[筛选] 断板股: {len(duanban)} 只")
    
    return {
        "lianban": lianban,
        "huiluo": huiluo,
        "duanban": duanban,
    }

# ========== 企业微信推送函数 ==========

def send_text_message(content):
    """发送文字消息到企业微信"""
    payload = {
        "msgtype": "text",
        "text": {"content": content}
    }
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(WEBHOOK_URL, headers=headers, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"发送文字消息失败: {e}")
        return None

def send_image(filepath):
    """发送图片到企业微信"""
    try:
        with open(filepath, 'rb') as f:
            image_data = f.read()
        
        base64_data = base64.b64encode(image_data).decode('utf-8')
        md5_value = hashlib.md5(image_data).hexdigest()
        
        payload = {
            "msgtype": "image",
            "image": {
                "base64": base64_data,
                "md5": md5_value
            }
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(WEBHOOK_URL, headers=headers, json=payload, timeout=30)
        return response.json()
    except Exception as e:
        print(f"发送图片失败: {e}")
        return None

# ========== 图片生成函数 ==========

def create_stock_image(title, stocks, filename, date_str):
    """生成精简版股票图片"""
    width = 800
    height = 1500
    
    img = Image.new('RGB', (width, height), color='#1a1a2e')
    draw = ImageDraw.Draw(img)
    
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 44)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 28)
        stock_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 30)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 22)
    except:
        title_font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        stock_font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # 标题背景
    draw.rectangle([(0, 0), (width, 90)], fill='#16213e')
    
    # 标题
    title_text = f"{title} - {date_str}"
    bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = bbox[2] - bbox[0]
    draw.text(((width - title_w) // 2, 22), title_text, fill='#e94560', font=title_font)
    
    # 表头
    draw.rectangle([(0, 90), (width, 140)], fill='#0f3460')
    draw.text((50, 96), "序号", fill='#ffffff', font=header_font)
    draw.text((200, 96), "股票名称", fill='#ffffff', font=header_font)
    draw.text((500, 96), "股票代码", fill='#ffffff', font=header_font)
    
    # 股票列表
    y = 148
    row_height = 52
    for i, stock in enumerate(stocks[:20], 1):
        if i % 2 == 0:
            draw.rectangle([(0, y-2), (width, y+row_height-2)], fill='#16213e')
        
        draw.text((60, y), str(i), fill='#eaeaea', font=stock_font)
        draw.text((200, y), stock['name'], fill='#eaeaea', font=stock_font)
        draw.text((500, y), stock['code'], fill='#00d9ff', font=stock_font)
        y += row_height
    
    # 底部
    draw.rectangle([(0, height-50), (width, height)], fill='#16213e')
    footer_text = f"数据日期: {date_str} | 来源: 同花顺/东方财富"
    bbox = draw.textbbox((0, 0), footer_text, font=small_font)
    footer_w = bbox[2] - bbox[0]
    draw.text(((width - footer_w) // 2, height-38), footer_text, fill='#888888', font=small_font)
    
    img.save(filename, 'PNG')
    print(f"已生成: {filename}")
    return filename

# ========== 主流程 ==========

def main():
    """主执行函数"""
    beijing_now = get_beijing_now()
    print(f"=== A股每日筛选任务开始 ===")
    print(f"当前时间(北京时间): {beijing_now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 检查是否为交易日
    if not is_trading_day():
        print("今日为非交易日，跳过执行")
        send_text_message(f"【A股筛选】{beijing_now.strftime('%Y-%m-%d')} 为非交易日，跳过执行")
        return
    
    date_str = beijing_now.strftime("%Y%m%d")
    date_display = beijing_now.strftime("%Y.%m.%d")
    
    print(f"交易日: {date_display}")
    
    # ===== Step 1: 获取数据 =====
    print("\n[Step 1] 获取人气榜数据...")
    renqi_data = get_renqi_data()
    if not renqi_data:
        print("人气榜数据为空，任务终止")
        send_text_message(f"【A股筛选】{date_display} 人气榜数据获取失败，任务终止")
        return
    
    time.sleep(1)
    
    print("\n[Step 2] 获取今日涨停数据...")
    zt_today = get_zt_pool(date_str)
    
    time.sleep(1)
    
    print("\n[Step 3] 获取昨日涨停数据...")
    zt_yesterday = get_yesterday_zt_pool(date_str)
    
    # ===== Step 2: 执行筛选 =====
    print("\n[Step 4] 执行筛选条件...")
    data = run_filters(renqi_data, zt_today, zt_yesterday)
    
    # ===== Step 3: 生成图片 =====
    print("\n[Step 5] 生成图片...")
    output_dir = "/workspace/stock_images"
    
    lianban_img = create_stock_image("连板股", data["lianban"], f"{output_dir}/连板_{date_str}.png", date_display)
    huiluo_img = create_stock_image("回调股", data["huiluo"], f"{output_dir}/回调_{date_str}.png", date_display)
    duanban_img = create_stock_image("断板股", data["duanban"], f"{output_dir}/断板_{date_str}.png", date_display)
    
    # ===== Step 4: 推送文字消息 =====
    print("\n[Step 6] 推送文字消息...")
    
    # 连板股消息
    lianban_text = f"【连板股 TOP{len(data['lianban'])} - {date_display}】\n条件：今日涨停 + 非ST\n按人气热度排名\n\n"
    for i, s in enumerate(data["lianban"][:20], 1):
        mark = f" {s.get('mark', '')}" if s.get('mark', '') else ""
        lianban_text += f"{i}. {s['name']}({s['code']}) {s.get('change_pct', 0):+.2f}%{mark}\n"
    send_text_message(lianban_text)
    
    # 回调股消息
    huiluo_text = f"【回调股 TOP{len(data['huiluo'])} - {date_display}】\n条件：今日涨8%以内 + 非ST + 20日内有涨停\n按人气热度排名\n\n"
    for i, s in enumerate(data["huiluo"][:20], 1):
        mark = f" {s.get('mark', '')}" if s.get('mark', '') else ""
        huiluo_text += f"{i}. {s['name']}({s['code']}) {s.get('change_pct', 0):+.2f}%{mark}\n"
    send_text_message(huiluo_text)
    
    # 断板股消息
    duanban_text = f"【断板股 TOP{len(data['duanban'])} - {date_display}】\n条件：昨日涨停 + 今日未涨停 + 非ST\n按人气热度排名\n\n"
    for i, s in enumerate(data["duanban"][:20], 1):
        ylbc = s.get('yesterday_lbc', 0)
        duanban_text += f"{i}. {s['name']}({s['code']}) {s.get('change_pct', 0):+.2f}% 昨日{ylbc}连板\n"
    send_text_message(duanban_text)
    
    # ===== Step 5: 推送图片 =====
    print("\n[Step 7] 推送图片...")
    send_image(lianban_img)
    send_image(huiluo_img)
    send_image(duanban_img)
    
    print("\n=== 任务完成 ===")
    finish_time = get_beijing_now().strftime('%H:%M:%S')
    send_text_message(f"【A股筛选】{date_display} {finish_time} 任务执行完成\n连板{len(data['lianban'])}只 | 回调{len(data['huiluo'])}只 | 断板{len(data['duanban'])}只")

if __name__ == "__main__":
    main()
