#!/usr/bin/env python3
"""
A股短线复盘PDF生成器（增强版）
含：情绪周期判定 + 龙头板块/个股 + 两模式操作建议
生成专业复盘报告并通过企业微信Webhook推送
"""

import json
import sys
import os
import time
import requests
from datetime import datetime, timedelta

# PDF生成
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ============== 字体设置 ==============
def register_chinese_font():
    """注册中文字体"""
    font_paths = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]
    
    for path in font_paths:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('ChineseFont', path, subfontIndex=0))
                return 'ChineseFont'
            except:
                try:
                    pdfmetrics.registerFont(TTFont('ChineseFont', path))
                    return 'ChineseFont'
                except:
                    continue
    
    # 尝试系统字体目录
    system_fonts = [
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ]
    for path in system_fonts:
        if os.path.exists(path):
            try:
                pdfmetrics.registerFont(TTFont('ChineseFont', path, subfontIndex=0))
                return 'ChineseFont'
            except:
                continue
    
    return None

CJK_FONT = register_chinese_font()
if not CJK_FONT:
    print("警告: 无法加载中文字体，PDF中文可能无法正常显示")
    CJK_FONT = 'Helvetica'

# ============== 颜色定义 ==============
PRIMARY_COLOR = HexColor('#1a365d')
ACCENT_COLOR = HexColor('#2b6cb0')
GREEN_COLOR = HexColor('#38a169')
RED_COLOR = HexColor('#e53e3e')
GRAY_COLOR = HexColor('#718096')
LIGHT_BG = HexColor('#f7fafc')

# ============== 样式定义 ==============
def get_styles():
    """获取PDF样式"""
    return {
        'title': ParagraphStyle(
            'Title', fontName=CJK_FONT, fontSize=26, leading=32,
            textColor=PRIMARY_COLOR, spaceAfter=12, alignment=TA_CENTER, wordWrap='CJK'
        ),
        'subtitle': ParagraphStyle(
            'Subtitle', fontName=CJK_FONT, fontSize=14, leading=18,
            textColor=GRAY_COLOR, spaceAfter=20, alignment=TA_CENTER, wordWrap='CJK'
        ),
        'h1': ParagraphStyle(
            'H1', fontName=CJK_FONT, fontSize=18, leading=24,
            textColor=PRIMARY_COLOR, spaceBefore=20, spaceAfter=10, wordWrap='CJK'
        ),
        'h2': ParagraphStyle(
            'H2', fontName=CJK_FONT, fontSize=14, leading=20,
            textColor=ACCENT_COLOR, spaceBefore=14, spaceAfter=8, wordWrap='CJK'
        ),
        'body': ParagraphStyle(
            'Body', fontName=CJK_FONT, fontSize=11, leading=18,
            textColor=HexColor('#2d3748'), spaceBefore=0, spaceAfter=8,
            firstLineIndent=0, wordWrap='CJK'
        ),
        'small': ParagraphStyle(
            'Small', fontName=CJK_FONT, fontSize=9, leading=13,
            textColor=GRAY_COLOR, spaceBefore=0, spaceAfter=6, wordWrap='CJK'
        ),
        'table_header': ParagraphStyle(
            'TableHeader', fontName=CJK_FONT, fontSize=10, leading=14,
            textColor=HexColor('#ffffff'), wordWrap='CJK', alignment=TA_CENTER
        ),
        'table_body': ParagraphStyle(
            'TableBody', fontName=CJK_FONT, fontSize=9, leading=13,
            wordWrap='CJK', alignment=TA_CENTER
        ),
        'table_body_small': ParagraphStyle(
            'TableBodySmall', fontName=CJK_FONT, fontSize=8, leading=11,
            wordWrap='CJK', alignment=TA_CENTER
        ),
        'positive': ParagraphStyle(
            'Positive', fontName=CJK_FONT, fontSize=9, leading=13,
            textColor=RED_COLOR, wordWrap='CJK', alignment=TA_CENTER
        ),
        'negative': ParagraphStyle(
            'Negative', fontName=CJK_FONT, fontSize=9, leading=13,
            textColor=GREEN_COLOR, wordWrap='CJK', alignment=TA_CENTER
        ),
        'red_text': ParagraphStyle(
            'RedText', fontName=CJK_FONT, fontSize=12, leading=18,
            textColor=RED_COLOR, spaceAfter=8, wordWrap='CJK'
        ),
    }

# ============== 文本标准化 ==============
def normalize_text(text):
    """标准化特殊字符"""
    if not text:
        return ""
    replacements = {
        '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2013': '-',
        '\u2014': '-', '\u2015': '-', '\u2212': '-', '\u00ad': '-',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text

# ============== 表格辅助函数 ==============
def create_table(data, col_widths=None, style=None):
    """创建表格"""
    if not data:
        return None
    
    styles = get_styles()
    # 包装单元格
    wrapped_data = []
    for i, row in enumerate(data):
        wrapped_row = []
        for cell in row:
            cell_str = str(cell) if cell is not None else ""
            cell_str = normalize_text(cell_str)
            
            # 第一行用表头样式（白字）
            if i == 0:
                wrapped_row.append(Paragraph(cell_str, styles['table_header']))
            elif isinstance(cell, str):
                if cell.startswith('+') or cell.startswith('↑'):
                    wrapped_row.append(Paragraph(cell_str, styles['positive']))
                elif cell.startswith('-') or cell.startswith('↓'):
                    wrapped_row.append(Paragraph(cell_str, styles['negative']))
                else:
                    wrapped_row.append(Paragraph(cell_str, styles['table_body']))
            else:
                wrapped_row.append(Paragraph(cell_str, styles['table_body']))
        wrapped_data.append(wrapped_row)
    
    table = Table(wrapped_data, colWidths=col_widths)
    
    # 表格样式
    ts = [
        ('BACKGROUND', (0, 0), (-1, 0), ACCENT_COLOR),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#ffffff')),
        ('FONTNAME', (0, 0), (-1, 0), CJK_FONT),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTNAME', (0, 1), (-1, -1), CJK_FONT),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
        ('BACKGROUND', (0, 1), (-1, -1), LIGHT_BG),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_BG, HexColor('#ffffff')]),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e2e8f0')),
    ]
    
    if style:
        ts.extend(style)
    
    table.setStyle(TableStyle(ts))
    return table

def create_table_ex(data, col_widths=None, header_color=None, small_font=False):
    """创建表格（支持自定义表头颜色和小字体）"""
    if not data:
        return None
    styles = get_styles()
    body_style = styles['table_body_small'] if small_font else styles['table_body']
    wrapped_data = []
    for i, row in enumerate(data):
        wrapped_row = []
        cell_style = styles['table_header'] if i == 0 else body_style
        for cell in row:
            cell_str = str(cell) if cell is not None else ""
            cell_str = normalize_text(cell_str)
            wrapped_row.append(Paragraph(cell_str, cell_style))
        wrapped_data.append(wrapped_row)

    table = Table(wrapped_data, colWidths=col_widths, repeatRows=1)
    hdr_color = header_color if header_color else ACCENT_COLOR
    ts = [
        ('BACKGROUND', (0, 0), (-1, 0), hdr_color),
        ('TEXTCOLOR', (0, 0), (-1, 0), HexColor('#ffffff')),
        ('FONTNAME', (0, 0), (-1, -1), CJK_FONT),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 8 if small_font else 9),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 0), (-1, 0), 8),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 5),
        ('TOPPADDING', (0, 1), (-1, -1), 5),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [LIGHT_BG, HexColor('#ffffff')]),
        ('GRID', (0, 0), (-1, -1), 0.5, HexColor('#e2e8f0')),
    ]
    table.setStyle(TableStyle(ts))
    return table

# ============== 分隔线 ==============
class Divider:
    """分隔线"""
    def __init__(self, width, height=1, color=HexColor('#e2e8f0'), space_before=6, space_after=10):
        self.width = width
        self.height = height
        self.color = color
        self.spaceBefore = space_before
        self.spaceAfter = space_after
    
    def wrap(self, *args):
        return (self.width, self.height)
    
    def draw(self):
        pass

def add_divider(width, height=1, color=HexColor('#e2e8f0'), space_before=6, space_after=10):
    """添加分隔线"""
    story = []
    story.append(Spacer(1, space_before))
    divider_style = ParagraphStyle(
        'Divider', fontName=CJK_FONT, fontSize=height,
        textColor=color, spaceBefore=0, spaceAfter=0
    )
    story.append(Paragraph(" " * 100, divider_style))
    story.append(Spacer(1, space_after))
    return story

# ============== 近期重大事项日历（未来两周） ==============

def get_default_events_calendar():
    """
    未来两周重大事项默认清单（带完整日期 YYYYMMDD，按报告日自动过滤14天窗口）
    格式: [日期, 类别, 事项, 说明, 重要性]
    外部 JSON 可通过 events_calendar 字段覆盖（格式相同，缺省时使用本清单）
    更新记录: 2026-08-26 依据公开信息整理
    """
    return [
        ["20260826", "财报", "英伟达 Q2 FY2027 财报", "美股盘后公布，一致预期营收920亿美元 / EPS 2.09美元，AI链风向标", "重磅"],
        ["20260826", "发射", "SpaceX · Starlink 发射", "猎鹰9 · 范登堡 · 一箭27星组网", "关注"],
        ["20260827", "上市", "希音 / 梅卡曼德 招股截止", "港股公开发售中午12:00截止", "关注"],
        ["20260830", "发射", "罗曼空间望远镜发射", "SpaceX猎鹰9 · 肯尼迪中心 · NASA新一代旗舰天文台", "重磅"],
        ["20260831", "财报", "A股中报披露截止", "半年报全部出齐，业绩雷与超预期集中兑现", "重磅"],
        ["20260831", "上市", "希音 / 梅卡曼德 暗盘", "上市前最后一个交易日暗盘交易", "关注"],
        ["20260901", "上市", "SHEIN 希音-W 港股上市", "0625.HK · 募资最高超154亿港元 · 年内最受关注IPO", "重磅"],
        ["20260901", "上市", "梅卡曼德机器人 港股上市", "9615.HK · 工业机器人 / 具身智能", "关注"],
        ["20260904", "宏观", "美国8月非农就业数据", "北京时间20:30 · 9月FOMC会前最后一份就业报告", "重磅"],
        ["20260908", "会议", "聚合智能产业发展大会2026", "武汉光谷 · 9/8-9 · 智能汽车 / 具身智能 / 低空经济", "关注"],
        ["20260909", "发布会", "苹果秋季发布会", "北京时间凌晨1:00 · iPhone 18系列 + 首款折叠屏iPhone Ultra", "重磅"],
        ["20260909", "会议", "2026服贸会开幕", "北京首钢园 · 9/9-13 · 全球服务贸易交易会", "关注"],
    ]

def filter_events_window(events, report_date_str=None):
    """
    过滤出报告日起未来14天内（含当天）的事项，按日期排序
    返回: (过滤后清单, 基准日期date对象)
    """
    base = None
    if report_date_str:
        for fmt in ("%Y%m%d", "%Y-%m-%d"):
            try:
                base = datetime.strptime(str(report_date_str), fmt).date()
                break
            except ValueError:
                continue
    if base is None:
        base = datetime.now().date()
    window_end = base + timedelta(days=14)

    result = []
    for ev in events:
        try:
            d = str(ev[0]).replace("-", "").replace(".", "")
            if len(d) != 8:
                continue
            ev_date = datetime.strptime(d, "%Y%m%d").date()
        except (ValueError, IndexError):
            continue
        if base <= ev_date <= window_end:
            result.append(ev)
    result.sort(key=lambda x: str(x[0]).replace("-", "").replace(".", ""))
    return result, base

def build_events_calendar_rows(events, base):
    """将事件清单转为表格行，日期列带相对天数标注"""
    rows = []
    for ev in events:
        try:
            d = str(ev[0]).replace("-", "").replace(".", "")
            ev_date = datetime.strptime(d, "%Y%m%d").date()
            dd = (ev_date - base).days
        except (ValueError, IndexError):
            continue
        d_display = f"{d[4:6]}月{d[6:8]}日"
        if dd == 0:
            d_display += "（今天）"
        elif dd == 1:
            d_display += "（明天）"
        else:
            d_display += f"（D+{dd}）"
        cat = ev[1] if len(ev) > 1 else ""
        title = ev[2] if len(ev) > 2 else ""
        detail = ev[3] if len(ev) > 3 else ""
        weight = ev[4] if len(ev) > 4 else "关注"
        rows.append([d_display, cat, title, detail, weight])
    return rows

# ============== PDF生成 ==============
def generate_pdf(data, output_path, report_date_str=None):
    """生成PDF报告（增强版：含情绪周期+龙头板块+两模式操作建议）"""
    styles = get_styles()

    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=0.6*inch,
        rightMargin=0.6*inch,
        topMargin=0.6*inch,
        bottomMargin=0.6*inch,
    )

    story = []
    content_width = A4[0] - 1.2*inch

    # ========== 封面 ==========
    story.append(Spacer(1, 0.8*inch))
    story.append(Paragraph(normalize_text(f"A股短线复盘"), styles['title']))
    story.append(Paragraph(normalize_text(data.get('date', '')), styles['subtitle']))
    story.append(Spacer(1, 0.3*inch))
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    story.append(Paragraph(normalize_text(f"生成时间: {current_time}"), styles['small']))
    story.append(PageBreak())

    # ========== 一、大盘概况 ==========
    story.append(Paragraph(normalize_text("一、大盘概况"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    index_data = data.get('index', [])
    if index_data:
        index_header = [["指数", "收盘", "涨跌幅", "成交额"]]
        index_table = create_table(index_header + index_data, col_widths=[1.8*inch, 1.4*inch, 1.2*inch, 1.2*inch])
        if index_table:
            story.append(index_table)
            story.append(Spacer(1, 0.15*inch))
    market_summary = data.get('market_summary', '')
    if market_summary:
        story.append(Paragraph(normalize_text(market_summary), styles['body']))
    story.append(Spacer(1, 0.15*inch))

    # ========== 二、资金流向 ==========
    story.append(Paragraph(normalize_text("二、资金流向"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    bx_data = data.get('bx', [])
    if bx_data:
        story.append(Paragraph(normalize_text("北向资金（沪深股通）"), styles['h2']))
        bx_header = [["方向", "金额", "说明"]]
        bx_table = create_table(bx_header + bx_data, col_widths=[1.5*inch, 1.5*inch, 2.6*inch])
        if bx_table:
            story.append(bx_table)
            story.append(Spacer(1, 0.1*inch))
    zl_data = data.get('zl', [])
    if zl_data:
        story.append(Paragraph(normalize_text("主力资金板块净流入排名"), styles['h2']))
        zl_header = [["板块", "净流入", "代表个股"]]
        zl_table = create_table(zl_header + zl_data, col_widths=[1.8*inch, 1.4*inch, 2.4*inch])
        if zl_table:
            story.append(zl_table)
    story.append(Spacer(1, 0.15*inch))

    # ========== 三、市场情绪 ==========
    story.append(Paragraph(normalize_text("三、市场情绪"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    qx_data = data.get('qx', [])
    if qx_data:
        qx_header = [["指标", "数值", "解读"]]
        qx_table = create_table(qx_header + qx_data, col_widths=[1.5*inch, 1.3*inch, 2.8*inch])
        if qx_table:
            story.append(qx_table)
            story.append(Spacer(1, 0.1*inch))
    qx_summary = data.get('qx_summary', '')
    if qx_summary:
        story.append(Paragraph(normalize_text(qx_summary), styles['body']))
    story.append(Spacer(1, 0.15*inch))

    # ========== 四、情绪周期判定（新增）==========
    cycle_current = data.get('cycle_current', '')
    if cycle_current:
        story.append(Paragraph(normalize_text("四、情绪周期判定"), styles['h1']))
        for _ in add_divider(content_width):
            story.append(_)
        story.append(Paragraph(normalize_text("当前周期：" + cycle_current), styles['red_text']))
        # 本周情绪周期演进表
        cycle_week = data.get('cycle_week', [])
        if cycle_week:
            story.append(Paragraph(normalize_text("本周情绪周期演进"), styles['h2']))
            cw_header = [["日期", "涨停", "跌停", "连板高度", "封板率", "晋级率", "阶段判定", "标志事件"]]
            cw_table = create_table_ex(cw_header + cycle_week, col_widths=[
                content_width*0.09, content_width*0.07, content_width*0.07, content_width*0.08,
                content_width*0.07, content_width*0.07, content_width*0.16, content_width*0.39], small_font=True)
            if cw_table:
                story.append(cw_table)
            story.append(Spacer(1, 0.08*inch))
        # 当日判定信号表
        cycle_judgment = data.get('cycle_judgment', [])
        if cycle_judgment:
            story.append(Paragraph(normalize_text("当日判定信号"), styles['h2']))
            cj_header = [["判定维度", "信号", "状态"]]
            cj_table = create_table_ex(cj_header + cycle_judgment, col_widths=[
                content_width*0.25, content_width*0.45, content_width*0.30])
            if cj_table:
                story.append(cj_table)
            story.append(Spacer(1, 0.05*inch))
        cycle_watch = data.get('cycle_watch', '')
        if cycle_watch:
            story.append(Paragraph(normalize_text(cycle_watch), styles['body']))
        story.append(Spacer(1, 0.15*inch))

    # ========== 五、龙头板块与龙头个股（新增）==========
    strong_sectors = data.get('strong_sectors', [])
    if strong_sectors:
        story.append(Paragraph(normalize_text("五、龙头板块与龙头个股"), styles['h1']))
        for _ in add_divider(content_width):
            story.append(_)
        story.append(Paragraph(normalize_text("强势板块（逆势/抗跌）"), styles['h2']))
        ss_header = [["板块", "强度", "催化逻辑", "龙头个股", "表现"]]
        ss_table = create_table_ex(ss_header + strong_sectors, col_widths=[
            content_width*0.15, content_width*0.08, content_width*0.30,
            content_width*0.20, content_width*0.27], small_font=True)
        if ss_table:
            story.append(ss_table)
        story.append(Spacer(1, 0.1*inch))
        ladder = data.get('ladder', [])
        if ladder:
            story.append(Paragraph(normalize_text("连板梯队（市场高度锚点）"), styles['h2']))
            ld_header = [["层级", "个股", "连板数", "定位", "风险提示"]]
            ld_table = create_table_ex(ld_header + ladder, col_widths=[
                content_width*0.10, content_width*0.20, content_width*0.12,
                content_width*0.28, content_width*0.30])
            if ld_table:
                story.append(ld_table)
            story.append(Spacer(1, 0.1*inch))
        risk_sectors = data.get('risk_sectors', [])
        if risk_sectors:
            story.append(Paragraph(normalize_text("退潮/风险板块（回避）"), styles['h2']))
            rs_header = [["板块", "状态", "代表个股", "回避原因"]]
            rs_table = create_table_ex(rs_header + risk_sectors, col_widths=[
                content_width*0.18, content_width*0.15, content_width*0.22, content_width*0.45],
                header_color=RED_COLOR)
            if rs_table:
                story.append(rs_table)
        story.append(Spacer(1, 0.15*inch))

    # ========== 六、热点题材 ==========
    story.append(Paragraph(normalize_text("六、热点题材"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    themes = data.get('themes', [])
    for theme in themes:
        theme_title = theme.get('title', '')
        theme_logic = theme.get('logic', '')
        theme_stocks = theme.get('stocks', [])
        if theme_title:
            story.append(Paragraph(normalize_text(theme_title), styles['h2']))
        if theme_logic:
            story.append(Paragraph(normalize_text(theme_logic), styles['body']))
        if theme_stocks:
            stocks_header = [["个股", "代码", "今日表现", "定位"]]
            stocks_data = stocks_header + theme_stocks
            stocks_table = create_table(stocks_data, col_widths=[1.5*inch, 1.1*inch, 1.3*inch, 1.7*inch])
            if stocks_table:
                story.append(stocks_table)
        story.append(Spacer(1, 0.08*inch))

    # ========== 七、消息面 ==========
    story.append(Paragraph(normalize_text("七、消息面"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    bad_news = data.get('bad_news', '')
    if bad_news:
        story.append(Paragraph(normalize_text("⚠️ 利空消息"), styles['h2']))
        for line in bad_news.split('\n'):
            if line.strip():
                story.append(Paragraph(normalize_text("• " + line.strip()), styles['body']))
        story.append(Spacer(1, 0.1*inch))
    good_news = data.get('good_news', '')
    if good_news:
        story.append(Paragraph(normalize_text("✅ 政策催化"), styles['h2']))
        for line in good_news.split('\n'):
            if line.strip():
                story.append(Paragraph(normalize_text("• " + line.strip()), styles['body']))
    story.append(Spacer(1, 0.15*inch))

    # ========== 八、近期重大事项日历（未来两周）==========
    raw_events = data.get('events_calendar', [])
    events, ev_base = filter_events_window(
        raw_events if raw_events else get_default_events_calendar(), report_date_str)
    if events:
        story.append(Paragraph(normalize_text("八、近期重大事项日历（未来两周）"), styles['h1']))
        for _ in add_divider(content_width):
            story.append(_)
        ev_rows = build_events_calendar_rows(events, ev_base)
        if ev_rows:
            ev_header = [["日期", "类别", "事项", "说明", "重要性"]]
            ev_table = create_table_ex(ev_header + ev_rows, col_widths=[
                content_width*0.16, content_width*0.08, content_width*0.24,
                content_width*0.42, content_width*0.10], small_font=True)
            if ev_table:
                story.append(ev_table)
        ev_note = data.get('events_note', '')
        if ev_note:
            story.append(Paragraph(normalize_text(ev_note), styles['body']))
        story.append(Spacer(1, 0.15*inch))

    # ========== 九、今日总结 ==========
    story.append(Paragraph(normalize_text("九、今日总结"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    features = data.get('features', '')
    if features:
        story.append(Paragraph(normalize_text("📌 今日核心特征"), styles['h2']))
        if isinstance(features, str):
            for line in features.split('\n'):
                if line.strip():
                    story.append(Paragraph(normalize_text("• " + line.strip()), styles['body']))
        elif isinstance(features, list):
            for i, feature in enumerate(features, 1):
                story.append(Paragraph(normalize_text(f"{i}. {feature}"), styles['body']))
        story.append(Spacer(1, 0.1*inch))
    opportunities = data.get('opportunities', '')
    if opportunities:
        story.append(Paragraph(normalize_text("💡 机会方向"), styles['h2']))
        if isinstance(opportunities, str):
            for line in opportunities.split('\n'):
                if line.strip():
                    story.append(Paragraph(normalize_text("• " + line.strip()), styles['body']))
        elif isinstance(opportunities, list):
            for i, opp in enumerate(opportunities, 1):
                story.append(Paragraph(normalize_text(f"{i}. {opp}"), styles['body']))
        story.append(Spacer(1, 0.1*inch))
    risks = data.get('risks', '')
    if risks:
        story.append(Paragraph(normalize_text("⚠️ 风险提示"), styles['h2']))
        if isinstance(risks, str):
            for line in risks.split('\n'):
                if line.strip():
                    story.append(Paragraph(normalize_text("• " + line.strip()), styles['body']))
        elif isinstance(risks, list):
            for i, risk in enumerate(risks, 1):
                story.append(Paragraph(normalize_text(f"{i}. {risk}"), styles['body']))
        story.append(Spacer(1, 0.1*inch))
    strategy = data.get('strategy', '')
    if strategy:
        story.append(Paragraph(normalize_text("📋 操作策略"), styles['h2']))
        story.append(Paragraph(normalize_text(strategy), styles['body']))
    story.append(PageBreak())

    # ========== 十、核心标的速览 ==========
    story.append(Paragraph(normalize_text("十、核心标的速览"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    quick_data = data.get('quick', [])
    if quick_data:
        quick_header = [["层级", "个股", "代码", "今日表现"]]
        quick_table_data = quick_header + quick_data
        quick_table = create_table(quick_table_data, col_widths=[1.0*inch, 1.5*inch, 1.1*inch, 2.0*inch])
        if quick_table:
            story.append(quick_table)

    # ========== 十、两模式操作建议与本周复盘反思（放最后，始终显示）==========
    # 内置默认速查表（防止执行session遗漏mode_speed字段时PDF缺失速查表）
    DEFAULT_MODE_SPEED = [
        ["周期阶段", "判断依据", "打板接力·操作", "打板·仓位", "龙回头·操作", "龙回头·仓位", "2万本金参考"],
        ["冰点期", "涨停<50只，连板<=2板，跌停>涨停，炸板率高", "空仓，极小仓试错新题材首板", "0-2成/快进快出", "空仓，无达标标的", "0", "0元，空仓等机会"],
        ["启动期", "涨停60-80只，连板突破3-4板，主线未明确", "轻仓试错首板/1进2", "1-3成/严格止损", "可做上一轮总龙头回头", "1-2成/10日线止损", "2000-4000元，轻仓试探"],
        ["发酵期", "涨停80-120只，连板4-5板，梯队成型", "加仓接力龙头2进3/3进4", "3-5成/5日线止损", "标的增多，可做断板回调龙头", "2-3成/10日线止损", "4000-6000元，小仓参与"],
        ["高潮期", "涨停120+只，连板6-8板+，封板率80%+", "重仓死磕龙头，捂股为王", "5-8成/不断板不减", "无标的可用（龙头还在连板）", "—", "打板可重仓1-1.5万"],
        ["分歧/退潮初期", "涨停持续减少，龙头首次断板，炸板增多", "减仓落袋，仅做首阴反包", "1-2成/严格止损", "黄金窗口！三信号齐全可重仓", "5-6成/10日线止损", "1-1.2万重仓，止损亏约1000元"],
        ["退潮深化期", "涨停<80只，连板高度持续压缩，跌停激增", "空仓避险，杜绝抄底", "0-1成", "大幅降频，只做最强总龙头", "1成/收紧至入场低点-3%", "2000元，快进快出"],
        ["退潮期末期", "涨停持续降，5/10日线破位，亏钱效应扩散", "空仓", "0", "空仓等待冰点信号", "0", "0元，空仓等待"],
    ]

    story.append(PageBreak())
    story.append(Paragraph(normalize_text("十一、两模式操作建议与本周复盘反思"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)

    # 当日两模式操作建议
    mode_today = data.get('mode_today', [])
    if mode_today:
        story.append(Paragraph(normalize_text("11.1 当日操作建议"), styles['h2']))
        mt_header = [["模式", "操作建议", "原因"]]
        mt_table = create_table_ex(mt_header + mode_today, col_widths=[
            content_width*0.12, content_width*0.22, content_width*0.66],
            header_color=RED_COLOR)
        if mt_table:
            story.append(mt_table)
        story.append(Spacer(1, 0.1*inch))
    else:
        # 默认提示
        story.append(Paragraph(normalize_text("11.1 当日操作建议"), styles['h2']))
        story.append(Paragraph(normalize_text("（请根据当前情绪周期参考下方速查表）"), styles['body']))
        story.append(Spacer(1, 0.1*inch))

    # 各情绪周期两模式操作建议速查表（永久参考，始终显示）
    # 如果JSON提供了mode_speed则用提供的，否则用内置默认值
    mode_speed = data.get('mode_speed', []) or DEFAULT_MODE_SPEED
    story.append(Paragraph(normalize_text("11.2 各情绪周期两模式操作建议速查表（永久参考）"), styles['h2']))
    num_cols = len(mode_speed[0]) if mode_speed else 5
    if num_cols >= 7:
        ms_widths = [content_width*0.08, content_width*0.16, content_width*0.16,
                     content_width*0.12, content_width*0.18, content_width*0.12, content_width*0.18]
    else:
        ms_widths = [content_width*0.15, content_width*0.22, content_width*0.15,
                     content_width*0.28, content_width*0.20]
    ms_table = create_table_ex(mode_speed, col_widths=ms_widths, small_font=True)
    if ms_table:
        story.append(ms_table)
    story.append(Spacer(1, 0.1*inch))

    # 本周复盘反思
    week_reflection = data.get('week_reflection', [])
    if week_reflection:
        story.append(Paragraph(normalize_text("11.3 本周复盘反思（两模式对照）"), styles['h2']))
        wr_header = [["日期", "周期阶段", "打板接力最优操作", "龙回头最优操作", "是否该操作"]]
        wr_table = create_table_ex(wr_header + week_reflection, col_widths=[
            content_width*0.10, content_width*0.12, content_width*0.28,
            content_width*0.30, content_width*0.20], small_font=True)
        if wr_table:
            story.append(wr_table)

    # ========== 十一、大事件日历（未来两周）==========
    calendar_data = data.get('calendar', [])
    calendar_note = data.get('calendar_note', '')
    if calendar_data or calendar_note:
        story.append(PageBreak())
        story.append(Paragraph(normalize_text("十一、大事件日历（未来两周）"), styles['h1']))
        for _ in add_divider(content_width):
            story.append(_)
        if calendar_data:
            cal_header = [["日期", "时间", "事件", "影响板块/关注点"]]
            cal_table = create_table_ex(cal_header + calendar_data, col_widths=[
                content_width*0.12, content_width*0.10, content_width*0.43, content_width*0.35], small_font=True)
            if cal_table:
                story.append(cal_table)
            story.append(Spacer(1, 0.1*inch))
        if calendar_note:
            story.append(Paragraph(normalize_text("📌 日历要点"), styles['h2']))
            if isinstance(calendar_note, str):
                for line in calendar_note.split('\n'):
                    if line.strip():
                        story.append(Paragraph(normalize_text("• " + line.strip()), styles['body']))
            elif isinstance(calendar_note, list):
                for item in calendar_note:
                    if item:
                        story.append(Paragraph(normalize_text("• " + str(item)), styles['body']))
            story.append(Spacer(1, 0.1*inch))

    # ========== 生成PDF ==========
    doc.build(story)
    print(f"PDF已生成: {output_path}")
    return output_path

# ============== 企业微信推送 ==============
WEBHOOK_KEY = "c62953cf-031b-4d0e-a99f-513593e55771"
UPLOAD_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key={WEBHOOK_KEY}&type=file"
SEND_URL = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={WEBHOOK_KEY}"

def push_to_wecom(file_path):
    """通过企业微信Webhook推送文件"""
    try:
        # 第一步：上传文件获取media_id
        with open(file_path, 'rb') as f:
            files = {'file': (os.path.basename(file_path), f, 'application/pdf')}
            response = requests.post(UPLOAD_URL, files=files, timeout=30)
        
        result = response.json()
        print(f"上传结果: {result}")
        
        if result.get('errcode') != 0:
            print(f"❌ 上传失败: {result}")
            return False
        
        media_id = result.get('media_id')
        
        # 第二步：用media_id发送文件消息
        payload = {
            "msgtype": "file",
            "file": {
                "media_id": media_id
            }
        }
        
        response = requests.post(SEND_URL, json=payload, timeout=30)
        result = response.json()
        
        if result.get('errcode') == 0:
            print("✅ 文件推送成功!")
            return True
        else:
            print(f"❌ 发送失败: {result}")
            return False
            
    except Exception as e:
        print(f"❌ 推送异常: {e}")
        return False

# ============== 主函数 ==============
def main():
    if len(sys.argv) < 3:
        print("用法: python build_report.py <JSON数据> <日期YYYYMMDD>")
        sys.exit(1)
    
    json_str = sys.argv[1]
    date_str = sys.argv[2]
    
    # 解析JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"JSON解析失败: {e}")
        sys.exit(1)
    
    # 输出文件路径
    output_dir = "/workspace"
    output_path = os.path.join(output_dir, f"A股短线复盘_{date_str}.pdf")
    
    # 生成PDF（传入报告日期用于事件日历窗口过滤）
    generate_pdf(data, output_path, date_str)
    
    # 推送
    print("\n开始推送PDF...")
    push_success = push_to_wecom(output_path)
    
    if not push_success:
        print("\n⚠️ 自动推送失败，请手动执行以下命令:")
        print(f'curl -F "file=@{output_path}" "{UPLOAD_URL}"')
        print(f'然后用返回的media_id发送: curl -X POST "{SEND_URL}" -H "Content-Type: application/json" -d \'{{"msgtype":"file","file":{{"media_id":"MEDIA_ID"}}}}\'''')

if __name__ == "__main__":
    main()
