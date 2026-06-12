#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from PIL import Image, ImageDraw, ImageFont
import os

def create_stock_image(title, stocks, filename):
    """生成精简版股票图片，只显示股票名称和代码"""
    # 图片尺寸 - 增加高度确保20行完整显示
    width = 800
    height = 1500
    
    # 创建图片
    img = Image.new('RGB', (width, height), color='#1a1a2e')
    draw = ImageDraw.Draw(img)
    
    # 尝试加载字体
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 44)
        header_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 28)
        stock_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 30)
        small_font = ImageFont.truetype("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc", 22)
    except:
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
            header_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            stock_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
            small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
        except:
            title_font = ImageFont.load_default()
            header_font = ImageFont.load_default()
            stock_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
    
    # 绘制标题背景
    draw.rectangle([(0, 0), (width, 90)], fill='#16213e')
    
    # 绘制标题
    title_text = f"{title} - 2026.06.12"
    bbox = draw.textbbox((0, 0), title_text, font=title_font)
    title_w = bbox[2] - bbox[0]
    draw.text(((width - title_w) // 2, 22), title_text, fill='#e94560', font=title_font)
    
    # 绘制表头
    draw.rectangle([(0, 90), (width, 140)], fill='#0f3460')
    draw.text((50, 96), "序号", fill='#ffffff', font=header_font)
    draw.text((200, 96), "股票名称", fill='#ffffff', font=header_font)
    draw.text((500, 96), "股票代码", fill='#ffffff', font=header_font)
    
    # 绘制股票列表 - 调整行高和间距
    y = 148
    row_height = 52
    for i, stock in enumerate(stocks[:20], 1):
        # 交替行背景色
        if i % 2 == 0:
            draw.rectangle([(0, y-2), (width, y+row_height-2)], fill='#16213e')
        
        # 序号
        draw.text((60, y), str(i), fill='#eaeaea', font=stock_font)
        
        # 股票名称
        draw.text((200, y), stock['name'], fill='#eaeaea', font=stock_font)
        
        # 股票代码
        draw.text((500, y), stock['code'], fill='#00d9ff', font=stock_font)
        
        y += row_height
    
    # 绘制底部信息
    draw.rectangle([(0, height-50), (width, height)], fill='#16213e')
    footer_text = "数据日期: 2026-06-12 | 来源: 同花顺/东方财富"
    bbox = draw.textbbox((0, 0), footer_text, font=small_font)
    footer_w = bbox[2] - bbox[0]
    draw.text(((width - footer_w) // 2, height-38), footer_text, fill='#888888', font=small_font)
    
    # 保存图片
    img.save(filename, 'PNG')
    print(f"已生成: {filename}")

# 条件1：连板股（今日涨停 + 非ST）按人气热度排序
lianban_stocks = [
    {"name": "宗申动力", "code": "001696"},
    {"name": "洛阳钼业", "code": "603993"},
    {"name": "中化国际", "code": "600500"},
    {"name": "和远气体", "code": "002971"},
    {"name": "铜陵有色", "code": "000630"},
    {"name": "航天发展", "code": "000547"},
    {"name": "金钼股份", "code": "601958"},
    {"name": "宿迁联盛", "code": "603065"},
    {"name": "恩捷股份", "code": "002812"},
    {"name": "中百集团", "code": "000759"},
    {"name": "方正科技", "code": "600601"},
    {"name": "泰晶科技", "code": "603738"},
    {"name": "盛龙股份", "code": "001257"},
    {"name": "中航西飞", "code": "000768"},
    {"name": "深桑达A", "code": "000032"},
    {"name": "多氟多", "code": "002407"},
    {"name": "云南锗业", "code": "002428"},
    {"name": "永杉锂业", "code": "603399"},
    {"name": "翔鹭钨业", "code": "002842"},
    {"name": "康强电子", "code": "002119"},
]

# 条件2：回调股（今日涨8%以内 + 非ST）按人气热度排序
huiluo_stocks = [
    {"name": "利通电子", "code": "603629"},
    {"name": "多氟多", "code": "002407"},
    {"name": "大唐发电", "code": "601991"},
    {"name": "风华高科", "code": "000636"},
    {"name": "亨通光电", "code": "600487"},
    {"name": "京东方A", "code": "000725"},
    {"name": "神剑股份", "code": "002361"},
    {"name": "华电辽能", "code": "600396"},
    {"name": "豫能控股", "code": "001896"},
    {"name": "达实智能", "code": "002421"},
    {"name": "天娱数科", "code": "002354"},
    {"name": "太极实业", "code": "600667"},
    {"name": "长电科技", "code": "600584"},
    {"name": "中钨高新", "code": "000657"},
    {"name": "远东股份", "code": "600869"},
    {"name": "香江控股", "code": "600162"},
    {"name": "金安国纪", "code": "002636"},
    {"name": "中际旭创", "code": "300308"},
    {"name": "三花智控", "code": "002050"},
    {"name": "云南锗业", "code": "002428"},
]

# 条件3：断板股（昨日涨停 + 今日未涨停 + 非ST）按人气热度排序
duanban_stocks = [
    {"name": "昊华科技", "code": "600378"},
    {"name": "康强电子", "code": "002119"},
    {"name": "红宝丽", "code": "002165"},
    {"name": "雅克科技", "code": "002409"},
    {"name": "新亚强", "code": "603155"},
    {"name": "天地源", "code": "600665"},
    {"name": "东安动力", "code": "600178"},
    {"name": "京基智农", "code": "000048"},
    {"name": "泰和新材", "code": "002254"},
    {"name": "春光科技", "code": "603657"},
    {"name": "亚盛集团", "code": "600108"},
    {"name": "博敏电子", "code": "603936"},
    {"name": "津投城开", "code": "600322"},
    {"name": "濮阳惠成", "code": "300481"},
    {"name": "六国化工", "code": "600470"},
    {"name": "三维化学", "code": "002469"},
    {"name": "金牛化工", "code": "600722"},
    {"name": "松霖科技", "code": "603992"},
    {"name": "江丰电子", "code": "300666"},
    {"name": "利德曼", "code": "300289"},
]

# 生成图片
create_stock_image("连板股", lianban_stocks, "/workspace/stock_images/连板_20260612.png")
create_stock_image("回调股", huiluo_stocks, "/workspace/stock_images/回调_20260612.png")
create_stock_image("断板股", duanban_stocks, "/workspace/stock_images/断板_20260612.png")

print("所有图片生成完成!")
