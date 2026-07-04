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

# ========== 数据获取：同花顺个股热度（兜底方案） ==========

def get_ths_hot_stock():
    """
    从同花顺数据中心获取个股热度排名（兜底方案）
    接口：同花顺数据中心-热门榜单
    返回: list[dict]，每个dict包含 code, name, rank, change_pct
    """
    url = "https://data.10jqka.com.cn/dataapi/limit_up/limit_up_pool"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://data.10jqka.com.cn/",
    }
    
    # 尝试从同花顺热门个股页面获取
    hot_url = "https://q.10jqka.com.cn/"
    params = {
        "query": "热门个股排名",
        "type": "query",
    }
    
    try:
        # 尝试同花顺问财接口获取热门个股
        wencai_url = "https://www.iwencai.com/unifiedwap/unified-wap/v2/result/get-robot-data"
        wencai_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.iwencai.com/",
        }
        wencai_params = {
            "question": "热门个股排名 今日",
            "perpage": 100,
            "page": 1,
            "secondary_intent": "stock",
            "log_info": '{"input_type":"typewrite"}',
            "source": "Ths_iwencai_Xuangu",
            "version": "2.0",
            "query_area": "block",
            "block_list": "",
            "add_info": '{"urp":{"scene":1,"company":1,"business":1},"contentType":"json","searchInfo":true}',
        }
        
        response = requests.post(wencai_url, json=wencai_params, headers=wencai_headers, timeout=15)
        data = response.json()
        
        if data.get("data") and data["data"].get("answer"):
            answer = data["data"]["answer"]
            # 解析JSON中的股票数据
            components = answer.get("components", [])
            for comp in components:
                if comp.get("data") and comp["data"].get("datas"):
                    items = comp["data"]["datas"]
                    result = []
                    for item in items:
                        code = item.get("code", "")
                        name = item.get("name", "")
                        # 尝试获取热度相关字段
                        hot_rank = item.get("rank", 0)
                        change_pct = 0
                        try:
                            change_pct = float(item.get("changepercent", 0))
                        except (ValueError, TypeError):
                            pass
                        
                        if code and name:
                            result.append({
                                "code": code,
                                "name": name,
                                "mark": "",
                                "rank": hot_rank if hot_rank else len(result) + 1,
                                "change_pct": change_pct,
                            })
                    
                    if result:
                        print(f"[同花顺热度] 获取到 {len(result)} 条数据")
                        return result
    except Exception as e:
        print(f"[同花顺热度] 请求失败: {e}")
    
    # 如果问财接口也失败，返回空
    print("[同花顺热度] 兜底方案未获取到数据")
    return []

def get_renqi_data_with_fallback():
    """
    获取人气排行榜数据，优先复盘网，失败时用同花顺热度兜底
    """
    data = get_renqi_data()
    if data:
        return data
    
    print("[人气榜] 复盘网数据为空，启用同花顺热度兜底方案...")
    time.sleep(2)
    return get_ths_hot_stock()

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

# ========== 数据获取：近N日涨停股候选池 ==========

def get_recent_zt_candidates(date_str, days=20):
    """
    获取近N个交易日内有过涨停的股票代码集合（用于回调股候选池）
    通过逐日查询涨停板API获取，跳过无数据的非交易日
    返回: dict {code: name}
    """
    today = datetime.strptime(date_str, "%Y%m%d")
    all_codes = {}
    
    for offset in range(1, days + 10):  # 多回退一些以跳过周末和节假日
        prev = today - timedelta(days=offset)
        prev_str = prev.strftime("%Y%m%d")
        
        url = "https://push2ex.eastmoney.com/getTopicZTPool"
        params = {
            "ut": "7eea3edcaed734bea9cbfc24409ed989",
            "dpt": "wz.ztzt",
            "Pageindex": "0",
            "Pagesize": "500",
            "sort": "fbt:asc",
            "date": prev_str,
            "_": str(int(time.time() * 1000)),
        }
        
        try:
            response = requests.get(url, params=params, headers=HEADERS, timeout=10)
            data = response.json()
            if data.get("data") and data["data"].get("pool"):
                for item in data["data"]["pool"]:
                    code = item.get("c", "")
                    name = item.get("n", "")
                    if "ST" not in name and code:
                        all_codes[code] = name
                # 已经获取了足够的天数（按交易日计）
                if len(all_codes) >= 50:  # 至少累积50只不同的股票
                    # 检查是否已覆盖足够交易日
                    pass
        except Exception:
            continue
        
        # 一旦覆盖了足够天数就停止
        if offset >= days + 5:
            break
    
    print(f"[近{days}日涨停候选] 共 {len(all_codes)} 只股票")
    return all_codes


# ========== 数据获取：批量实时行情（腾讯API） ==========

def get_batch_realtime(codes):
    """
    批量获取股票实时行情（腾讯API）
    参数: codes - 股票代码列表
    返回: dict {code: {name, price, change_pct, volume, amount}}
    """
    if not codes:
        return {}
    
    tc_list = [_get_tencent_code(c) for c in codes]
    result = {}
    
    # 腾讯API每次最多约50只，分批查询
    batch_size = 50
    for i in range(0, len(tc_list), batch_size):
        batch = tc_list[i:i + batch_size]
        url = "https://qt.gtimg.cn/q=" + ",".join(batch)
        
        try:
            response = requests.get(url, headers=HEADERS, timeout=10)
            text = response.text
            
            # 解析每行数据
            for line in text.strip().split("\n"):
                if not line.strip() or "=" not in line:
                    continue
                # 格式: v_sz000536="51~华映科技~000536~..."
                var_name = line.split("=")[0].strip()
                value = line.split("=", 1)[1].strip().strip('"').strip(";")
                parts = value.split("~")
                if len(parts) >= 32:
                    code = parts[2]
                    name = parts[1]
                    try:
                        price = float(parts[3])
                    except ValueError:
                        price = 0
                    try:
                        change_pct = float(parts[32])
                    except (ValueError, IndexError):
                        change_pct = 0
                    try:
                        volume = float(parts[6])
                    except (ValueError, IndexError):
                        volume = 0
                    try:
                        amount = float(parts[37]) if len(parts) > 37 else 0
                    except (ValueError, IndexError):
                        amount = 0
                    try:
                        turnover_rate = float(parts[38]) if len(parts) > 38 else 0  # 换手率
                    except (ValueError, IndexError):
                        turnover_rate = 0
                    
                    result[code] = {
                        "name": name,
                        "price": price,
                        "change_pct": change_pct,
                        "volume": volume,
                        "amount": amount,
                        "turnover_rate": turnover_rate,
                    }
        except Exception as e:
            print(f"[批量行情] 批次查询失败: {e}")
            continue
        
        time.sleep(0.3)  # 批次间间隔
    
    return result

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

# ========== 情绪周期分析模块 ==========

# 市场宽度缓存，避免get_dieting_count等函数重复请求全市场数据
_breadth_cache = None

def get_market_breadth():
    """
    获取全市场涨跌家数统计
    返回: dict {up, down, flat, up5, down5, zt, dt, total}
    """
    global _breadth_cache
    if _breadth_cache is not None:
        return _breadth_cache

    up = down = flat = up5 = down5 = zt = dt = 0
    total = 0

    for page in range(1, 60):
        url = "https://push2.eastmoney.com/api/qt/clist/get"
        params = {
            "pn": page, "pz": 200, "po": 1, "np": 1,
            "ut": "bd1d9c04089390ee585d6f098e6a7c91",
            "fltt": 2, "invt": 2, "fid": "f3",
            "fs": "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23",
            "fields": "f2,f3,f12,f14",
        }
        try:
            resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
            data = resp.json()
            items = data.get("data", {}).get("diff", [])
            if not items:
                break
            for item in items:
                pct = item.get("f3")
                if pct is None:
                    continue
                total += 1
                if pct > 0:
                    up += 1
                elif pct < 0:
                    down += 1
                else:
                    flat += 1
                if pct >= 9.8:
                    zt += 1
                if pct <= -9.8:
                    dt += 1
                if pct >= 5:
                    up5 += 1
                if pct <= -5:
                    down5 += 1
            if items[-1].get("f3", 0) < -2:
                break
        except Exception:
            break

    # 如果东财接口失败，用腾讯接口补全
    if total == 0:
        print("[市场宽度] 东财接口失败，尝试腾讯接口...")
        try:
            url_tencent = "https://web.ifzq.gtimg.cn/appstock/app/rank/rank?cmd=rank&market=0&ranktype=5&stocktype=0&page=0&num=5000&_var=rank_data"
            resp = requests.get(url_tencent, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}, timeout=15)
            text = resp.text
            start = text.index("{")
            data = json.loads(text[start:])
            stock_list = data.get("data", {}).get("rank", {}).get("data", [])
            for stock in stock_list:
                if len(stock) < 5:
                    continue
                pct = stock[4]
                if pct is None:
                    continue
                total += 1
                if pct > 0:
                    up += 1
                elif pct < 0:
                    down += 1
                else:
                    flat += 1
                if pct >= 9.8:
                    zt += 1
                if pct <= -9.8:
                    dt += 1
                if pct >= 5:
                    up5 += 1
                if pct <= -5:
                    down5 += 1
        except Exception as e:
            print(f"[市场宽度] 腾讯接口也失败: {e}")

    # 如果东财和腾讯都失败，用新浪接口作为第三备选
    if total == 0:
        print("[市场宽度] 尝试新浪接口...")
        try:
            sina_headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": "https://finance.sina.com.cn/",
            }
            for page in range(1, 61):
                url = (f"https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/"
                       f"Market_Center.getHQNodeData?page={page}&num=100&sort=symbol&asc=1"
                       f"&node=hs_a&symbol=&_s_r_a=auto")
                resp = requests.get(url, headers=sina_headers, timeout=15)
                items = resp.json()
                if not items:
                    break
                for item in items:
                    pct = item.get("changepercent")
                    if pct is None:
                        continue
                    pct = float(pct)
                    total += 1
                    if pct > 0:
                        up += 1
                    elif pct < 0:
                        down += 1
                    else:
                        flat += 1
                    if pct >= 9.8:
                        zt += 1
                    if pct <= -9.8:
                        dt += 1
                    if pct >= 5:
                        up5 += 1
                    if pct <= -5:
                        down5 += 1
        except Exception as e:
            print(f"[市场宽度] 新浪接口也失败: {e}")

    print(f"[市场宽度] 上涨{up} 下跌{down} 涨停{zt} 跌停{dt}")
    result = {
        "up": up, "down": down, "flat": flat,
        "up5": up5, "down5": down5,
        "zt": zt, "dt": dt, "total": total,
    }
    _breadth_cache = result
    return result


def get_index_data():
    """获取主要指数实时数据"""
    indices = {
        "1.000001": "上证指数",
        "0.399001": "深证成指",
        "0.399006": "创业板指",
    }
    result = {}

    # 先尝试东财接口
    try:
        secids = ",".join(indices.keys())
        url = f"https://push2.eastmoney.com/api/qt/ulist.np/get?fields=f2,f3,f4,f6,f12,f14&secids={secids}"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        data = resp.json()
        for item in data.get("data", {}).get("diff", []):
            name = item.get("f14", "")
            price = item.get("f2", 0) / 100
            pct = item.get("f3", 0) / 100
            amount = item.get("f6", 0) / 100000000
            result[name] = {"price": price, "pct": pct, "amount": amount}
    except Exception as e:
        print(f"[指数] 东财接口失败: {e}")

    # 如果东财失败，用腾讯接口
    if not result:
        print("[指数] 尝试腾讯接口...")
        for secid, name in indices.items():
            try:
                url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={secid}"
                resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"}, timeout=10)
                text = resp.text
                start = text.index("{")
                data = json.loads(text[start:])
                stock_data = data.get("data", {}).get(secid, {}).get("data", {})
                if stock_data:
                    price = stock_data.get("price", 0)
                    prev_close = stock_data.get("prevClose", 0)
                    pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
                    result[name] = {"price": price, "pct": pct, "amount": 0}
            except Exception as e:
                print(f"[指数] 腾讯接口获取{name}失败: {e}")

    # 如果东财和腾讯都失败，用新浪指数接口作为第三备选
    if not result:
        print("[指数] 尝试新浪指数接口...")
        sina_headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn/",
        }
        sina_indices = {
            "sh000001": "上证指数",
            "sz399001": "深证成指",
            "sz399006": "创业板指",
            "sh000688": "科创50",
        }
        try:
            codes = ",".join(sina_indices.keys())
            url = f"https://hq.sinajs.cn/list={codes}"
            resp = requests.get(url, headers=sina_headers, timeout=10)
            resp.encoding = "gbk"
            for line in resp.text.strip().split("\n"):
                # 格式: var hq_str_sh000001="上证指数,4031.34,4028.89,...";
                m = re.search(r'hq_str_(\w+)="(.+)"', line)
                if not m:
                    continue
                code = m.group(1)
                content = m.group(2)
                data = content.split(",")
                if len(data) < 10:
                    continue
                name = sina_indices.get(code, data[0])
                try:
                    price = float(data[1])
                    prev_close = float(data[2])
                    amount = float(data[9]) / 100000000  # 成交额转为亿元
                except (ValueError, IndexError):
                    continue
                pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
                result[name] = {"price": price, "pct": pct, "amount": amount}
        except Exception as e:
            print(f"[指数] 新浪指数接口失败: {e}")

    return result


def get_zhaban_count(date_str):
    """获取炸板数（涨停后打开的）"""
    url = "https://push2ex.eastmoney.com/getTopicZBPool"
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": "0",
        "Pagesize": "500",
        "date": date_str,
        "_": str(int(time.time() * 1000)),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        pool = data.get("data", {}).get("pool", [])
        return len(pool)
    except Exception:
        # 炸板数据难以从新浪获取，返回-1表示数据不可用
        # (返回0会被误认为"封板率100%"导致评分虚高)
        return -1


def get_dieting_count(date_str):
    """获取跌停数"""
    url = "https://push2ex.eastmoney.com/getTopicDTPool"
    params = {
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "dpt": "wz.ztzt",
        "Pageindex": "0",
        "Pagesize": "500",
        "date": date_str,
        "_": str(int(time.time() * 1000)),
    }
    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = resp.json()
        pool = data.get("data", {}).get("pool", [])
        return len(pool)
    except Exception:
        # 东财接口失败，从市场宽度获取跌停数（复用缓存避免重复请求全市场数据）
        try:
            breadth = get_market_breadth()
            dt = breadth.get("dt", 0)
            print(f"[跌停] 东财接口失败，从市场宽度获取跌停数: {dt}")
            return dt
        except Exception as e:
            print(f"[跌停] fallback也失败: {e}")
            return 0


def analyze_sentiment_cycle(zt_today, zt_yesterday, breadth, zhaban, dieting):
    """
    判断当前市场情绪周期
    返回: dict {cycle, score, details}
    """
    zt_count = len(zt_today)
    dt_count = dieting
    up = breadth.get("up", 0)
    down = breadth.get("down", 0)
    total = breadth.get("total", 0)
    zhaban_count = zhaban

    # ===== 数据有效性校验 =====
    data_quality = "正常"
    # 跌停数据缺失: dt为0且有涨停股，但市场宽度接口失败(total=0)说明跌停数据缺失
    dt_data_missing = (dt_count == 0 and zt_count > 0 and total == 0)
    # 炸板数据不可用: 返回-1表示接口失败
    zhaban_unavailable = (zhaban_count == -1)
    # 涨跌数据缺失: 上涨下跌均为0
    updown_data_missing = (up == 0 and down == 0)
    if dt_data_missing or zhaban_unavailable or updown_data_missing:
        data_quality = "部分数据缺失"

    # 连板高度
    max_lbc = max([s.get("lbc", 1) for s in zt_today], default=0)

    # 连板晋级率：昨日连板今日继续涨停的比例
    yesterday_zt_codes = {s["code"] for s in zt_yesterday}
    today_zt_codes = {s["code"] for s in zt_today}
    jinji_count = len(yesterday_zt_codes & today_zt_codes)
    jinji_rate = jinji_count / len(yesterday_zt_codes) * 100 if yesterday_zt_codes else 0

    # 炸板率（数据不可用时标记为-1，不参与正常评分计算）
    if zhaban_unavailable:
        zhaban_rate = -1
    else:
        zhaban_rate = zhaban_count / (zt_count + zhaban_count) * 100 if (zt_count + zhaban_count) > 0 else 0

    # 涨跌比（数据缺失时不应计算为99，标记为-1）
    if updown_data_missing:
        up_down_ratio = -1
    else:
        up_down_ratio = up / down if down > 0 else 99

    # ===== 评分系统（0-100，越高越热） =====
    score = 0

    # 涨停数 (0-25分)
    if zt_count >= 100:
        score += 25
    elif zt_count >= 70:
        score += 20
    elif zt_count >= 50:
        score += 15
    elif zt_count >= 30:
        score += 10
    else:
        score += 5

    # 跌停数 (0-20分，跌停越多分越低)
    if dt_data_missing:
        # 数据缺失时给中等分，避免误判为"无跌停"满分导致评分虚高
        score += 10
    elif dt_count <= 5:
        score += 20
    elif dt_count <= 15:
        score += 15
    elif dt_count <= 30:
        score += 10
    elif dt_count <= 50:
        score += 5
    else:
        score += 0

    # 连板高度 (0-20分)
    if max_lbc >= 6:
        score += 20
    elif max_lbc >= 4:
        score += 15
    elif max_lbc >= 3:
        score += 10
    elif max_lbc >= 2:
        score += 5
    else:
        score += 0

    # 晋级率 (0-20分)
    if jinji_rate >= 60:
        score += 20
    elif jinji_rate >= 40:
        score += 15
    elif jinji_rate >= 25:
        score += 10
    elif jinji_rate >= 10:
        score += 5
    else:
        score += 0

    # 涨跌比 (0-15分)
    if updown_data_missing:
        # 数据缺失时给中等分，避免误判为"涨跌比极高"满分导致评分虚高
        score += 8
    elif up_down_ratio >= 3:
        score += 15
    elif up_down_ratio >= 2:
        score += 12
    elif up_down_ratio >= 1:
        score += 8
    elif up_down_ratio >= 0.5:
        score += 4
    else:
        score += 0

    # 炸板率（数据不可用时不参与正常评分计算，改为给中等分10以中性处理）
    if zhaban_unavailable:
        score += 10

    # ===== 周期判断 =====
    if score >= 80:
        cycle = "高潮期"
        cycle_desc = "市场极度亢奋，连板高度高、晋级率高、涨跌比大。注意：高潮期往往是风险累积期，随时可能退潮。"
        advice = "持股待涨，但不宜追高连板。注意首阴信号，做好撤退准备。"
    elif score >= 60:
        cycle = "震荡期"
        cycle_desc = "市场情绪中性，涨停和跌停都不极端，板块轮动为主。"
        advice = "可以正常做龙回头低吸，注意板块切换节奏。"
    elif score >= 40:
        cycle = "退潮期"
        cycle_desc = "连板开始断裂，炸板率升高，亏钱效应扩散。高位股补跌风险大。"
        advice = "控制仓位，回避高位连板股。只做低位首板或确定性回调。"
    else:
        cycle = "冰点期"
        cycle_desc = "涨停稀少、跌停增多、连板高度极低，市场恐慌情绪蔓延。"
        advice = "多看少动，等待情绪修复信号（涨停回升到60+、跌停骤降）。冰点后往往有回暖反弹。"

    return {
        "cycle": cycle,
        "cycle_desc": cycle_desc,
        "advice": advice,
        "score": score,
        "zt_count": zt_count,
        "dt_count": dt_count,
        "max_lbc": max_lbc,
        "jinji_rate": jinji_rate,
        "zhaban_rate": zhaban_rate,
        "up_down_ratio": up_down_ratio,
        "up": up,
        "down": down,
        "data_quality": data_quality,
    }


def create_sentiment_image(sentiment, index_data, date_str, filename):
    """生成情绪周期分析图片"""
    width = 800
    height = 1000

    img = Image.new('RGB', (width, height), color='#1a1a2e')
    draw = ImageDraw.Draw(img)

    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 44)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 28)
        stock_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 30)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 22)
        big_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 56)
    except:
        title_font = header_font = stock_font = small_font = big_font = ImageFont.load_default()

    # 标题
    draw.rectangle([(0, 0), (width, 90)], fill='#16213e')
    title_text = f"情绪周期分析 - {date_str}"
    bbox = draw.textbbox((0, 0), title_text, font=title_font)
    draw.text(((width - (bbox[2]-bbox[0])) // 2, 22), title_text, fill='#e94560', font=title_font)

    y = 110

    # 情绪周期判定
    cycle = sentiment["cycle"]
    cycle_colors = {
        "高潮期": "#ff4444",
        "震荡期": "#ffaa00",
        "退潮期": "#4488ff",
        "冰点期": "#00ddff",
    }
    cycle_color = cycle_colors.get(cycle, "#ffffff")

    draw.text((50, y), "当前周期:", fill='#888888', font=header_font)
    draw.text((280, y-8), cycle, fill=cycle_color, font=big_font)
    y += 70

    # 评分条
    score = sentiment["score"]
    draw.text((50, y), f"情绪评分: {score}/100", fill='#eaeaea', font=header_font)
    y += 40
    bar_x, bar_y, bar_w, bar_h = 50, y, 700, 20
    draw.rectangle([(bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h)], fill='#333333')
    fill_w = int(bar_w * score / 100)
    draw.rectangle([(bar_x, bar_y), (bar_x + fill_w, bar_y + bar_h)], fill=cycle_color)
    y += 40

    # 分隔线
    draw.line([(50, y), (750, y)], fill='#333355', width=1)
    y += 20

    # 核心指标
    draw.text((50, y), "核心指标", fill='#e94560', font=header_font)
    y += 40

    metrics = [
        ("涨停数", f"{sentiment['zt_count']} 只", "#ff4444" if sentiment['zt_count'] >= 70 else "#ffaa00" if sentiment['zt_count'] >= 40 else "#4488ff"),
        ("跌停数", f"{sentiment['dt_count']} 只", "#ff4444" if sentiment['dt_count'] >= 30 else "#ffaa00" if sentiment['dt_count'] >= 10 else "#00dd44"),
        ("连板高度", f"{sentiment['max_lbc']} 板", "#ff4444" if sentiment['max_lbc'] >= 5 else "#ffaa00" if sentiment['max_lbc'] >= 3 else "#4488ff"),
        ("晋级率", f"{sentiment['jinji_rate']:.0f}%", "#00dd44" if sentiment['jinji_rate'] >= 50 else "#ffaa00" if sentiment['jinji_rate'] >= 25 else "#ff4444"),
        ("炸板率", f"{sentiment['zhaban_rate']:.0f}%", "#ff4444" if sentiment['zhaban_rate'] >= 40 else "#ffaa00" if sentiment['zhaban_rate'] >= 20 else "#00dd44"),
        ("涨跌比", f"{sentiment['up_down_ratio']:.1f}", "#00dd44" if sentiment['up_down_ratio'] >= 2 else "#ffaa00" if sentiment['up_down_ratio'] >= 1 else "#ff4444"),
        ("上涨家数", f"{sentiment['up']}", "#00dd44"),
        ("下跌家数", f"{sentiment['down']}", "#ff4444"),
    ]

    for label, value, color in metrics:
        draw.text((60, y), label, fill='#aaaaaa', font=stock_font)
        draw.text((350, y), value, fill=color, font=stock_font)
        y += 42

    y += 10
    draw.line([(50, y), (750, y)], fill='#333355', width=1)
    y += 20

    # 指数概况
    draw.text((50, y), "指数概况", fill='#e94560', font=header_font)
    y += 40

    for name, info in index_data.items():
        pct = info["pct"]
        color = "#ff4444" if pct > 0 else "#00dd44" if pct < 0 else "#aaaaaa"
        text = f"{name}  {info['price']:.2f}  {pct:+.2f}%  额:{info['amount']:.0f}亿"
        draw.text((60, y), text, fill=color, font=stock_font)
        y += 38

    y += 10
    draw.line([(50, y), (750, y)], fill='#333355', width=1)
    y += 20

    # 操作建议
    draw.text((50, y), "操作建议", fill='#e94560', font=header_font)
    y += 40

    # 自动换行
    advice = sentiment["advice"]
    max_chars_per_line = 28
    for i in range(0, len(advice), max_chars_per_line):
        line = advice[i:i+max_chars_per_line]
        draw.text((60, y), line, fill='#eaeaea', font=small_font)
        y += 30

    # 底部
    draw.rectangle([(0, height-50), (width, height)], fill='#16213e')
    footer = f"数据日期: {date_str} | 情绪评分: {score}/100"
    bbox = draw.textbbox((0, 0), footer, font=small_font)
    draw.text(((width - (bbox[2]-bbox[0])) // 2, height-38), footer, fill='#888888', font=small_font)

    img.save(filename, 'PNG')
    print(f"已生成: {filename}")
    return filename

# ========== 数据获取：个股历史K线（腾讯API） ==========

def _get_tencent_code(stock_code):
    """将纯数字代码转为腾讯代码格式：sh600xxx / sz000xxx"""
    if stock_code.startswith("6"):
        return f"sh{stock_code}"
    else:
        return f"sz{stock_code}"

def get_stock_kline(stock_code, days=20):
    """
    获取个股近N日日K线数据（腾讯前复权）
    返回: list[dict]，每条包含 date, open, close, high, low, volume, change_pct
    """
    tc = _get_tencent_code(stock_code)
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    params = {
        "param": f"{tc},day,,,{days},qfq",
        "_": str(int(time.time() * 1000)),
    }
    
    try:
        response = requests.get(url, params=params, headers=HEADERS, timeout=10)
        data = response.json()
    except Exception as e:
        return []
    
    if data.get("code") != 0 or not data.get("data"):
        return []
    
    stock_data = data["data"].get(tc)
    if not stock_data or not stock_data.get("qfqday"):
        # 尝试不带复权的 day
        stock_data = data["data"].get(tc, {})
        raw = stock_data.get("day") or stock_data.get("qfqday") or []
    else:
        raw = stock_data["qfqday"]
    
    if not raw:
        return []
    
    result = []
    for i, line in enumerate(raw):
        if len(line) < 6:
            continue
        close_price = float(line[2])
        change_pct = 0.0
        if i > 0:
            prev_close = float(raw[i - 1][2])
            if prev_close > 0:
                change_pct = (close_price - prev_close) / prev_close * 100
        
        result.append({
            "date": line[0],
            "open": float(line[1]),
            "close": close_price,
            "high": float(line[3]),
            "low": float(line[4]),
            "volume": float(line[5]),
            "change_pct": change_pct,
        })
    
    return result

def check_near_high(stock_code, days=10):
    """
    检查近N日内股价是否接近或突破过近3个月高点
    判断标准：近N日最高价 >= 近3个月最高价的90%
    """
    klines = get_stock_kline(stock_code, days=60)
    if len(klines) < 2:
        return False
    
    # 近3个月（约60个交易日）最高价
    max_high_3m = max(k["high"] for k in klines)
    if max_high_3m <= 0:
        return False
    
    # 近N日最高价
    recent_klines = klines[-days:] if len(klines) >= days else klines
    max_high_recent = max(k["high"] for k in recent_klines)
    
    return max_high_recent >= max_high_3m * 0.9

def check_had_zt_in_days(stock_code, days=20):
    """检查近N日内是否有涨停（涨幅>=9.8%）"""
    klines = get_stock_kline(stock_code, days=days)
    for k in klines:
        if k["change_pct"] >= 9.8:
            return True
    return False

def check_volume_expand(stock_code):
    """检查今日成交量是否放大（对比前5日均量）"""
    klines = get_stock_kline(stock_code, days=10)
    if len(klines) < 6:
        return True  # 数据不足，默认通过
    
    today_volume = klines[-1]["volume"]
    avg_volume = sum(k["volume"] for k in klines[-6:-1]) / 5
    
    if avg_volume <= 0:
        return True
    return today_volume >= avg_volume * 1.2  # 放大20%以上

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

def build_unified_hotness_rank(renqi_data, candidate_codes):
    """
    构建统一的人气热度排名
    - 有复盘网数据的股票：使用复盘网实际人气排名
    - 无复盘网数据的股票：按换手率排名作为热度代理
    返回: dict {code: (rank, mark, change_pct)}
    """
    # 复盘网人气排名
    renqi_map = {}
    for item in renqi_data:
        renqi_map[item["code"]] = (item["rank"], item.get("mark", ""), item.get("change_pct", 0))
    
    # 不在人气榜的股票：获取换手率排名
    outside_codes = [c for c in candidate_codes if c not in renqi_map]
    
    if outside_codes:
        print(f"[人气排名] 获取 {len(outside_codes)} 只非人气榜股票的实时数据...")
        realtime = get_batch_realtime(outside_codes)
        
        # 按换手率降序排列，给它们分配排名
        # 复盘网人气榜最大排名大约99，所以从100开始
        turnover_ranked = []
        for code, data in realtime.items():
            turnover = data.get("turnover_rate", 0)
            change_pct = data.get("change_pct", 0)
            name = data.get("name", "")
            if turnover > 0 or change_pct != 0:
                turnover_ranked.append((code, turnover, change_pct, name))
        
        turnover_ranked.sort(key=lambda x: -x[1])  # 换手率降序
        for rank_offset, (code, turnover, change_pct, name) in enumerate(turnover_ranked):
            renqi_map[code] = (100 + rank_offset, "", change_pct)
    
    return renqi_map


def run_filters(renqi_data, zt_today, zt_yesterday, date_str):
    """
    执行三个筛选条件
    条件1（连板）：今日涨停 + 10日内接近3个月高点 + 非ST + 主板，按人气排名前20
    条件2（回调）：今日涨0-8% + 成交额放大 + 20日内有涨停 + 20日内接近3个月高点 + 非ST + 主板，按人气排名前20
    条件3（断板）：昨日涨停 + 今日未涨停 + 20日内接近3个月高点 + 非ST + 主板，按人气排名前20
    
    策略：先从全量候选池中按条件筛选，再按人气排名排序取前20。
    """
    
    zt_today_codes = set(s["code"] for s in zt_today)
    zt_yesterday_codes = set(s["code"] for s in zt_yesterday)
    zt_today_map = {s["code"]: s for s in zt_today}
    zt_yesterday_map = {s["code"]: s for s in zt_yesterday}
    
    # ===== 回调股：收集候选池并获取实时数据 =====
    print("\n[Step 回调] 收集近20日涨停候选...")
    recent_zt_candidates = get_recent_zt_candidates(date_str, days=20)
    
    # 收集所有需要排名的候选股
    all_candidate_codes = set(c for c in recent_zt_candidates)
    all_candidate_codes.update(s["code"] for s in zt_today)
    all_candidate_codes.update(s["code"] for s in zt_yesterday)
    
    # 构建统一的人气排名（复盘网数据 + 换手率代理）
    print("[人气排名] 构建统一热度排名...")
    hotness_rank = build_unified_hotness_rank(renqi_data, list(all_candidate_codes))
    
    # ===== 条件1：连板股 =====
    # 今日涨停 + 10日内接近3个月高点 + 非ST + 主板
    lianban = []
    for s in zt_today:
        code = s["code"]
        name = s["name"]
        
        if filter_st(name):
            continue
        if not is_main_board(code):
            continue
        if not check_near_high(code, days=10):
            continue
        
        rank_info = hotness_rank.get(code, (9999, "", s.get("change_pct", 0)))
        lianban.append({
            "name": name,
            "code": code,
            "change_pct": s.get("change_pct", 0),
            "lbc": s.get("lbc", 0),
            "mark": rank_info[1],
            "rank": rank_info[0],
        })
    
    lianban.sort(key=lambda x: x["rank"])
    lianban = lianban[:20]
    print(f"[筛选] 连板股: {len(lianban)} 只")
    
    # ===== 条件2：回调股 =====
    # 今日涨0-8% + 今日未涨停 + 昨日未涨停 + 成交额放大 + 20日内有涨停 + 20日内接近3个月高点 + 非ST + 主板
    # 从全量近20日涨停池筛选，换手率数据已在hotness_rank中
    realtime_huiluo = get_batch_realtime(list(recent_zt_candidates.keys()))
    
    huiluo = []
    for code, name in recent_zt_candidates.items():
        rt = realtime_huiluo.get(code)
        if not rt:
            continue
        
        change_pct = rt["change_pct"]
        if change_pct <= 0 or change_pct > 8.0:
            continue
        # 排除今日涨停的股票（涨停股应在连板列表中，不属于回调）
        if code in zt_today_codes:
            continue
        # 排除昨日涨停的股票（昨日涨停今日未涨停属于断板，不属于回调）
        if code in zt_yesterday_codes:
            continue
        if filter_st(name):
            continue
        if not is_main_board(code):
            continue
        # 20日内有涨停已经保证了（来自候选池）
        if not check_near_high(code, days=20):
            continue
        if not check_volume_expand(code):
            continue
        
        rank_info = hotness_rank.get(code, (9999, "", change_pct))
        huiluo.append({
            "name": name,
            "code": code,
            "change_pct": change_pct,
            "mark": rank_info[1],
            "rank": rank_info[0],
        })
    
    huiluo.sort(key=lambda x: x["rank"])
    huiluo = huiluo[:20]
    print(f"[筛选] 回调股: {len(huiluo)} 只")
    
    # ===== 条件3：断板股 =====
    # 昨日涨停 + 今日未涨停 + 20日内接近3个月高点 + 非ST + 主板
    duanban = []
    for s in zt_yesterday:
        code = s["code"]
        name = s["name"]
        
        if code in zt_today_codes:
            continue
        if filter_st(name):
            continue
        if not is_main_board(code):
            continue
        if not check_near_high(code, days=20):
            continue
        
        rank_info = hotness_rank.get(code, (9999, "", 0))
        duanban.append({
            "name": name,
            "code": code,
            "change_pct": rank_info[2],
            "yesterday_lbc": s.get("lbc", 0),
            "mark": rank_info[1],
            "rank": rank_info[0],
        })
    
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
    footer_text = f"数据日期: {date_str}"
    bbox = draw.textbbox((0, 0), footer_text, font=small_font)
    footer_w = bbox[2] - bbox[0]
    draw.text(((width - footer_w) // 2, height-38), footer_text, fill='#888888', font=small_font)
    
    img.save(filename, 'PNG')
    print(f"已生成: {filename}")
    return filename

# ========== N字反包选股（第四类，新增，不改动原有三类逻辑）==========

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


def get_nzi_realtime_detail(codes):
    """
    批量获取实时行情（含PE、成交额）
    腾讯API: parts[39]=PE, parts[37]=成交额(万元), parts[38]=换手率
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


def get_nzi_recent_zt_dates(date_str, num_days=4):
    """获取最近N个交易日的日期列表（跳过周末）"""
    today = datetime.strptime(date_str, "%Y%m%d")
    dates = []
    checked = 0
    offset = 0
    while len(dates) < num_days and checked < num_days + 10:
        offset += 1
        d = today - timedelta(days=offset)
        if d.weekday() >= 5:
            continue
        dates.append(d.strftime("%Y%m%d"))
        checked += 1
    return dates


def get_nzi_zt_pool(date_str):
    """获取涨停板数据（含hybk行业板块字段）"""
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
            })
        return result
    except Exception as e:
        print(f"[N字反包] 获取{date_str}涨停板失败: {e}")
        return []


def run_nzi_filter(date_str, max_count=20):
    """
    N字反包选股（V2逻辑，满分30分评分）
    条件：主板 + 近4天有涨停且今天断板 + 断板≥2天 + 上升趋势 + 缩量企稳MA5 + 不破MA10 + 热门概念
    返回: list[dict]（含name, code, score等，兼容create_stock_image）
    """
    print("\n[N字反包] 开始筛选...")

    recent_dates = get_nzi_recent_zt_dates(date_str, num_days=4)
    print(f"[N字反包] 回溯日期: {recent_dates}")

    all_zt = {}
    sector_zt_count = {}

    for d in recent_dates:
        pool = get_nzi_zt_pool(d)
        print(f"[N字反包] {d}: {len(pool)} 只涨停")
        for item in pool:
            code = item["code"]
            hybk = item.get("hybk", "")
            if code not in all_zt:
                all_zt[code] = {"name": item["name"], "zt_dates": [d],
                                "lbc_max": item["lbc"], "hybk": hybk}
            else:
                all_zt[code]["zt_dates"].append(d)
                all_zt[code]["lbc_max"] = max(all_zt[code]["lbc_max"], item["lbc"])
            if hybk:
                sector_zt_count[hybk] = sector_zt_count.get(hybk, 0) + 1
        time.sleep(0.5)

    today_pool = get_nzi_zt_pool(date_str)
    today_zt_codes = set(item["code"] for item in today_pool)

    candidates = []
    for code, info in all_zt.items():
        if code in today_zt_codes:
            continue
        if not is_main_board(code):
            continue
        candidates.append({"code": code, "name": info["name"], "hybk": info["hybk"],
                          "zt_dates": info["zt_dates"], "lbc_max": info["lbc_max"]})

    print(f"[N字反包] 断板候选: {len(candidates)} 只")

    qualified = []
    for c in candidates:
        code = c["code"]
        klines = get_stock_kline(code, days=30)
        if not klines or len(klines) < 20:
            continue

        closes = [k["close"] for k in klines]
        vols = [k["volume"] for k in klines]
        lows = [k["low"] for k in klines]

        zt_idx = -1
        for i in range(len(klines) - 1, 0, -1):
            chg = (closes[i] - closes[i-1]) / closes[i-1] * 100
            if chg >= 9.8:
                zt_idx = i
                break
        if zt_idx == -1:
            continue

        lianban = 0
        for i in range(zt_idx, 0, -1):
            chg = (closes[i] - closes[i-1]) / closes[i-1] * 100
            if chg >= 9.8:
                lianban += 1
            else:
                break

        days_after = len(klines) - 1 - zt_idx
        if days_after < 2:
            continue

        ma5 = sum(closes[-5:]) / 5
        ma10 = sum(closes[-10:]) / 10
        ma20 = sum(closes[-20:]) / 20

        if not (ma5 > ma10 > ma20):
            continue

        price = closes[-1]
        ma5_diff = (price - ma5) / ma5 * 100
        if abs(ma5_diff) > 5:
            continue

        if lows[-1] < ma10 * 0.98:
            continue

        vol_recent_3 = sum(vols[-3:]) / 3
        vol_zt = vols[zt_idx]
        vol_ratio = vol_recent_3 / vol_zt if vol_zt > 0 else 1
        if vol_ratio > 1.3:
            continue

        max_drop = 0
        for i in range(zt_idx + 1, len(klines)):
            drop = (closes[i] - closes[zt_idx]) / closes[zt_idx] * 100
            max_drop = min(max_drop, drop)
        if max_drop < -12:
            continue

        today_chg = (closes[-1] - closes[-2]) / closes[-2] * 100
        if today_chg < -5:
            continue

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

        rt_data = get_nzi_realtime_detail([code])
        r = rt_data.get(code, {})
        pe = r.get("pe", 0)
        amount = r.get("amount_yi", 0)
        turnover = r.get("turnover_rate", 0)

        # ===== 评分（满分30）=====
        score = 0
        if 2 <= days_after <= 4:
            score += 3
        elif days_after >= 5:
            score += 1
        if abs(ma5_diff) <= 3:
            score += 3
        elif abs(ma5_diff) <= 5:
            score += 1
        if vol_ratio < 0.7:
            score += 3
        elif vol_ratio < 1.0:
            score += 2
        elif vol_ratio < 1.2:
            score += 1
        if lianban >= 2:
            score += 2
        if max_drop > -5:
            score += 2
        elif max_drop > -8:
            score += 1
        if price > ma10:
            score += 1
        if (ma5 - ma10) / ma10 * 100 > 1:
            score += 1
        if pe > 0:
            if pe <= 20:
                score += 4
            elif pe <= 40:
                score += 3
            elif pe <= 80:
                score += 2
            elif pe <= 150:
                score += 1
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
        same_sector = sector_zt_count.get(sector, 0)
        if same_sector >= 5:
            score += 3
        elif same_sector >= 3:
            score += 2
        elif same_sector >= 2:
            score += 1

        qualified.append({
            "name": c["name"], "code": code, "score": score,
            "hot_cat": hot_cat, "pe": pe, "price": r.get("price", price),
            "amount": amount, "turnover": turnover, "lianban": lianban,
            "days_after": days_after, "today_chg": r.get("change_pct", today_chg),
        })
        time.sleep(0.1)

    qualified.sort(key=lambda x: -x["score"])
    result = qualified[:max_count]

    print(f"[N字反包] 符合条件: {len(qualified)} 只，取前{len(result)}只")
    for i, s in enumerate(result, 1):
        print(f"  {i:02d}. {s['name']}({s['code']}) [{s['hot_cat']}] 评分:{s['score']}/30 PE:{s['pe']:.0f}")

    return result

# ========== 主流程 ==========

def main():
    """主执行函数"""
    beijing_now = get_beijing_now()
    print(f"=== A股每日筛选任务开始 ===")
    print(f"当前时间(北京时间): {beijing_now.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 检查是否为交易日
    if not is_trading_day():
        print("今日为非交易日，跳过执行")
        return
    
    date_str = beijing_now.strftime("%Y%m%d")
    date_display = beijing_now.strftime("%Y.%m.%d")
    
    print(f"交易日: {date_display}")
    
    # ===== Step 1: 获取数据 =====
    print("\n[Step 1] 获取人气榜数据...")
    renqi_data = get_renqi_data_with_fallback()
    if not renqi_data:
        print("人气榜数据为空，任务终止")
        return
    
    time.sleep(1)
    
    print("\n[Step 2] 获取今日涨停数据...")
    zt_today = get_zt_pool(date_str)
    
    time.sleep(1)
    
    print("\n[Step 3] 获取昨日涨停数据...")
    zt_yesterday = get_yesterday_zt_pool(date_str)
    
    # ===== Step 2: 执行筛选 =====
    print("\n[Step 4] 执行筛选条件...")
    data = run_filters(renqi_data, zt_today, zt_yesterday, date_str)
    
    # ===== Step 3: 生成图片 =====
    print("\n[Step 5] 生成图片...")
    output_dir = "/workspace/stock_images"
    
    lianban_img = create_stock_image("连板股", data["lianban"], f"{output_dir}/连板_{date_str}.png", date_display)
    huiluo_img = create_stock_image("回调股", data["huiluo"], f"{output_dir}/回调_{date_str}.png", date_display)
    duanban_img = create_stock_image("断板股", data["duanban"], f"{output_dir}/断板_{date_str}.png", date_display)

    # ===== Step 5.2: N字反包选股（第四类，新增）=====
    print("\n[Step 5.2] N字反包选股...")
    nzi_stocks = run_nzi_filter(date_str)
    nzi_img = create_stock_image("N字反包", nzi_stocks, f"{output_dir}/N字反包_{date_str}.png", date_display)

    # ===== Step 5.5: 情绪周期分析（不再生成/推送图片，复盘PDF已包含） =====
    print("\n[Step 5.5] 情绪周期分析（仅日志，不生成图片）...")
    breadth = get_market_breadth()
    index_data = get_index_data()
    zhaban = get_zhaban_count(date_str)
    dieting = get_dieting_count(date_str)

    sentiment = analyze_sentiment_cycle(zt_today, zt_yesterday, breadth, zhaban, dieting)
    print(f"[情绪周期] {sentiment['cycle']} (评分:{sentiment['score']}/100)")
    print(f"  涨停:{sentiment['zt_count']} 跌停:{sentiment['dt_count']} 连板高度:{sentiment['max_lbc']}板")
    print(f"  晋级率:{sentiment['jinji_rate']:.0f}% 炸板率:{sentiment['zhaban_rate']:.0f}% 涨跌比:{sentiment['up_down_ratio']:.1f}")

    # ===== Step 6: 推送图片（不再推送情绪周期图片） =====
    print("\n[Step 6] 推送图片...")
    send_image(lianban_img)
    send_image(huiluo_img)
    send_image(duanban_img)
    send_image(nzi_img)

    print("\n=== 任务完成 ===")
    finish_time = get_beijing_now().strftime('%H:%M:%S')
    print(f"{date_display} {finish_time} 任务执行完成")
    print(f"  情绪周期: {sentiment['cycle']} (评分:{sentiment['score']}/100)")
    print(f"  连板{len(data['lianban'])}只 | 回调{len(data['huiluo'])}只 | 断板{len(data['duanban'])}只 | N字反包{len(nzi_stocks)}只")

if __name__ == "__main__":
    main()
