#!/usr/bin/env python3
"""
A股短线复盘PDF生成器
生成专业复盘报告并通过企业微信Webhook推送
"""

import json
import sys
import os
import time
import requests
from datetime import datetime

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
        'positive': ParagraphStyle(
            'Positive', fontName=CJK_FONT, fontSize=9, leading=13,
            textColor=GREEN_COLOR, wordWrap='CJK', alignment=TA_CENTER
        ),
        'negative': ParagraphStyle(
            'Negative', fontName=CJK_FONT, fontSize=9, leading=13,
            textColor=RED_COLOR, wordWrap='CJK', alignment=TA_CENTER
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
    
    # 包装单元格
    wrapped_data = []
    for i, row in enumerate(data):
        wrapped_row = []
        for cell in row:
            cell_str = str(cell) if cell is not None else ""
            cell_str = normalize_text(cell_str)
            
            # 判断颜色
            if isinstance(cell, str):
                if cell.startswith('+') or cell.startswith('↑'):
                    wrapped_row.append(Paragraph(cell_str, get_styles()['positive']))
                elif cell.startswith('-') or cell.startswith('↓'):
                    wrapped_row.append(Paragraph(cell_str, get_styles()['negative']))
                else:
                    wrapped_row.append(Paragraph(cell_str, get_styles()['table_body']))
            else:
                wrapped_row.append(Paragraph(cell_str, get_styles()['table_body']))
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
    
    # 简单实现：使用带背景色的段落模拟分隔线
    divider_style = ParagraphStyle(
        'Divider', fontName=CJK_FONT, fontSize=height,
        textColor=color, spaceBefore=0, spaceAfter=0
    )
    story.append(Paragraph(" " * 100, divider_style))
    story.append(Spacer(1, space_after))
    return story

# ============== PDF生成 ==============
def generate_pdf(data, output_path):
    """生成PDF报告"""
    styles = get_styles()
    
    # 页面设置
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
    
    # 副标题
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    story.append(Paragraph(normalize_text(f"生成时间: {current_time}"), styles['small']))
    story.append(PageBreak())
    
    # ========== 大盘概况 ==========
    story.append(Paragraph(normalize_text("一、大盘概况"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    
    # 指数表格
    index_data = data.get('index', [])
    if index_data:
        index_table = create_table(index_data, col_widths=[1.8*inch, 1.4*inch, 1.2*inch, 1.2*inch])
        if index_table:
            story.append(index_table)
            story.append(Spacer(1, 0.15*inch))
    
    # 大盘描述
    market_summary = data.get('market_summary', '')
    if market_summary:
        story.append(Paragraph(normalize_text(market_summary), styles['body']))
    
    story.append(Spacer(1, 0.15*inch))
    
    # ========== 资金流向 ==========
    story.append(Paragraph(normalize_text("二、资金流向"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    
    # 北向资金
    bx_data = data.get('bx', [])
    if bx_data:
        story.append(Paragraph(normalize_text("北向资金（沪深股通）"), styles['h2']))
        bx_table = create_table(bx_data, col_widths=[1.5*inch, 1.5*inch, 2.6*inch])
        if bx_table:
            story.append(bx_table)
            story.append(Spacer(1, 0.1*inch))
    
    # 主力资金
    zl_data = data.get('zl', [])
    if zl_data:
        story.append(Paragraph(normalize_text("主力资金板块净流入排名"), styles['h2']))
        zl_table = create_table(zl_data, col_widths=[1.8*inch, 1.4*inch, 2.4*inch])
        if zl_table:
            story.append(zl_table)
    
    story.append(Spacer(1, 0.15*inch))
    
    # ========== 市场情绪 ==========
    story.append(Paragraph(normalize_text("三、市场情绪"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    
    # 情绪指标
    qx_data = data.get('qx', [])
    if qx_data:
        qx_table = create_table(qx_data, col_widths=[1.5*inch, 1.3*inch, 2.8*inch])
        if qx_table:
            story.append(qx_table)
            story.append(Spacer(1, 0.1*inch))
    
    # 情绪小结
    qx_summary = data.get('qx_summary', '')
    if qx_summary:
        story.append(Paragraph(normalize_text(qx_summary), styles['body']))
    
    story.append(Spacer(1, 0.15*inch))
    
    # ========== 热点题材 ==========
    story.append(Paragraph(normalize_text("四、热点题材"), styles['h1']))
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
            # 主板标的表格
            stocks_header = [["个股", "代码", "今日表现", "定位"]]
            stocks_data = stocks_header + theme_stocks
            stocks_table = create_table(stocks_data, col_widths=[1.5*inch, 1.1*inch, 1.3*inch, 1.7*inch])
            if stocks_table:
                story.append(stocks_table)
        story.append(Spacer(1, 0.08*inch))
    
    # ========== 消息面 ==========
    story.append(Paragraph(normalize_text("五、消息面"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    
    # 利空消息
    bad_news = data.get('bad_news', '')
    if bad_news:
        story.append(Paragraph(normalize_text("⚠️ 利空消息"), styles['h2']))
        # 按换行分割
        for line in bad_news.split('\n'):
            if line.strip():
                story.append(Paragraph(normalize_text("• " + line.strip()), styles['body']))
        story.append(Spacer(1, 0.1*inch))
    
    # 政策催化
    good_news = data.get('good_news', '')
    if good_news:
        story.append(Paragraph(normalize_text("✅ 政策催化"), styles['h2']))
        for line in good_news.split('\n'):
            if line.strip():
                story.append(Paragraph(normalize_text("• " + line.strip()), styles['body']))
    
    story.append(Spacer(1, 0.15*inch))
    
    # ========== 今日总结 ==========
    story.append(Paragraph(normalize_text("六、今日总结"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    
    # 核心特征
    features = data.get('features', [])
    if features:
        story.append(Paragraph(normalize_text("📌 今日核心特征"), styles['h2']))
        for i, feature in enumerate(features, 1):
            story.append(Paragraph(normalize_text(f"{i}. {feature}"), styles['body']))
        story.append(Spacer(1, 0.1*inch))
    
    # 机会方向
    opportunities = data.get('opportunities', [])
    if opportunities:
        story.append(Paragraph(normalize_text("💡 机会方向"), styles['h2']))
        for i, opp in enumerate(opportunities, 1):
            story.append(Paragraph(normalize_text(f"{i}. {opp}"), styles['body']))
        story.append(Spacer(1, 0.1*inch))
    
    # 风险提示
    risks = data.get('risks', [])
    if risks:
        story.append(Paragraph(normalize_text("⚠️ 风险提示"), styles['h2']))
        for i, risk in enumerate(risks, 1):
            story.append(Paragraph(normalize_text(f"{i}. {risk}"), styles['body']))
        story.append(Spacer(1, 0.1*inch))
    
    # 操作策略
    strategy = data.get('strategy', '')
    if strategy:
        story.append(Paragraph(normalize_text("📋 操作策略"), styles['h2']))
        story.append(Paragraph(normalize_text(strategy), styles['body']))
    
    story.append(PageBreak())
    
    # ========== 核心标的速览 ==========
    story.append(Paragraph(normalize_text("七、核心标的速览"), styles['h1']))
    for _ in add_divider(content_width):
        story.append(_)
    
    quick_data = data.get('quick', [])
    if quick_data:
        quick_header = [["层级", "个股", "代码", "今日表现"]]
        quick_table_data = quick_header + quick_data
        quick_table = create_table(quick_table_data, col_widths=[1.0*inch, 1.5*inch, 1.1*inch, 2.0*inch])
        if quick_table:
            story.append(quick_table)
    
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
        
        # 第二步：用media_id发送文件消息（注意send_url和upload_url不同）
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
    
    # 生成PDF
    generate_pdf(data, output_path)
    
    # 推送
    print("\n开始推送PDF...")
    push_success = push_to_wecom(output_path)
    
    if not push_success:
        print("\n⚠️ 自动推送失败，请手动执行以下命令:")
        print(f'curl -F "file=@{output_path}" "{UPLOAD_URL}"')
        print(f'然后用返回的media_id发送: curl -X POST "{SEND_URL}" -H "Content-Type: application/json" -d \'{{"msgtype":"file","file":{{"media_id":"MEDIA_ID"}}}}\'''')

if __name__ == "__main__":
    main()
