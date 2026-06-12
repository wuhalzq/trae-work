#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import base64
import hashlib
import requests
import json

def send_image(filepath, webhook_key):
    """通过企业微信Webhook发送图片"""
    with open(filepath, 'rb') as f:
        image_data = f.read()
    
    base64_data = base64.b64encode(image_data).decode('utf-8')
    md5_value = hashlib.md5(image_data).hexdigest()
    
    url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
    payload = {
        "msgtype": "image",
        "image": {
            "base64": base64_data,
            "md5": md5_value
        }
    }
    
    headers = {"Content-Type": "application/json"}
    response = requests.post(url, headers=headers, data=json.dumps(payload))
    return response.json()

webhook_key = "c62953cf-031b-4d0e-a99f-513593e55771"

# 发送三张图片
result1 = send_image("/workspace/stock_images/连板_20260612.png", webhook_key)
print(f"连板图片发送结果: {result1}")

result2 = send_image("/workspace/stock_images/回调_20260612.png", webhook_key)
print(f"回调图片发送结果: {result2}")

result3 = send_image("/workspace/stock_images/断板_20260612.png", webhook_key)
print(f"断板图片发送结果: {result3}")
