#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
微信机器人 - 自动接收视频、上传到COS、创建分析任务
需要安装: pip3 install itchat cos-python-sdk-v5 requests
"""

import itchat
import os
import sys
import requests
import json
from datetime import datetime
from qcloud_cos import CosConfig, CosS3Client

# COS配置
COS_BUCKET = os.environ.get('COS_BUCKET', 'tennis-ai-1411340868')
COS_REGION = os.environ.get('COS_REGION', 'ap-shanghai')
COS_PREFIX = os.environ.get('COS_PREFIX', 'private-ai-learning/raw_videos')

# 回调服务配置
CALLBACK_SERVICE_URL = os.environ.get('CALLBACK_SERVICE_URL', 'http://122.152.207.136:5003/wechat/video')
TASK_STATUS_URL = os.environ.get('TASK_STATUS_URL', 'http://122.152.207.136:5003/task/status')

# COS客户端（延迟初始化）
cos_client = None

def get_cos_client():
    """获取COS客户端（延迟初始化）"""
    global cos_client
    if cos_client is None:
        secret_id = os.environ.get('COS_SECRET_ID', '')
        secret_key = os.environ.get('COS_SECRET_KEY', '')
        if not secret_id or not secret_key:
            raise ValueError("COS_SECRET_ID 和 COS_SECRET_KEY 环境变量必须设置")
        config = CosConfig(Region=COS_REGION, SecretId=secret_id, SecretKey=secret_key)
        cos_client = CosS3Client(config)
    return cos_client

def upload_to_cos(local_path, file_name):
    """上传文件到腾讯云COS"""
    try:
        client = get_cos_client()
        date = datetime.now().strftime("%Y-%m-%d")
        cos_key = f"{COS_PREFIX}/{date}/{int(datetime.now().timestamp())}_{file_name}"

        print(f"上传到COS: {cos_key}")

        with open(local_path, 'rb') as fp:
            response = client.put_object(
                Bucket=COS_BUCKET,
                Body=fp,
                Key=cos_key,
                ContentType='video/mp4'
            )
        
        cos_url = f"https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com/{cos_key}"
        print(f"✅ 上传成功: {cos_url}")
        
        return cos_url
        
    except Exception as e:
        print(f"❌ 上传失败: {e}")
        return None


def create_analysis_task(cos_url, cos_key, file_name, file_size_mb, user_id):
    """调用回调服务创建分析任务"""
    try:
        print(f"[Callback] 调用回调服务创建任务...")
        
        response = requests.post(
            CALLBACK_SERVICE_URL,
            data={
                'user_id': user_id,
                'cos_url': cos_url,
                'cos_key': cos_key,
                'file_name': file_name,
                'file_size_mb': file_size_mb
            }
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"[Callback] ❌ 回调服务返回错误: {response.status_code}")
            return {'success': False, 'error': response.text}
        
    except Exception as e:
        print(f"[Callback] ❌ 创建任务失败: {e}")
        return {'success': False, 'error': str(e)}


def query_task_status(task_id):
    """查询任务状态"""
    try:
        response = requests.get(f"{TASK_STATUS_URL}/{task_id}")
        return response.json()
    except Exception as e:
        return {'error': str(e)}

@itchat.msg_register(itchat.content.VIDEO)
def handle_video(msg):
    """处理视频消息"""
    print(f"\n{'='*50}")
    print(f"收到视频消息!")
    print(f"来自: {msg['FromUserName']}")
    print(f"文件名: {msg['FileName']}")
    print(f"{'='*50}")
    
    try:
        # 下载视频
        print("下载视频中...")
        local_path = msg['Text'](msg['FileName'])
        print(f"✅ 下载完成: {local_path}")
        
        # 获取文件大小
        file_size = os.path.getsize(local_path)
        print(f"文件大小: {file_size / 1024 / 1024:.2f} MB")
        
        # 上传到COS
        cos_url = upload_to_cos(local_path, msg['FileName'])
        
        if cos_url:
            # 提取COS key
            cos_key = cos_url.replace(f"https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com/", "")
            
            # 创建分析任务
            itchat.send("✅ 视频已上传，正在创建分析任务...", msg['FromUserName'])
            
            task_result = create_analysis_task(
                cos_url, 
                cos_key, 
                msg['FileName'], 
                file_size / (1024 * 1024),
                msg['FromUserName']
            )
            
            if task_result.get('success'):
                task_id = task_result.get('task_id')
                reply = f"""✅ 视频已接收并开始分析

📊 任务ID: {task_id}
⏱️ 状态: 分析中...

分析完成后，发送 "查询 {task_id}" 查看结果"""
                itchat.send(reply, msg['FromUserName'])
            else:
                reply = f"""⚠️ 视频已上传，但创建分析任务失败

COS地址: {cos_url}
错误: {task_result.get('error', '未知错误')}

请稍后重试或联系管理员"""
                itchat.send(reply, msg['FromUserName'])
        else:
            itchat.send("❌ 上传失败", msg['FromUserName'])
            
    except Exception as e:
        print(f"❌ 处理失败: {e}")
        itchat.send(f"❌ 处理失败: {str(e)}", msg['FromUserName'])

@itchat.msg_register(itchat.content.TEXT)
def handle_text(msg):
    """处理文字消息"""
    print(f"收到消息: {msg['Text']}")
    text = msg['Text'].strip()
    
    if text.lower() in ['help', '帮助']:
        reply = """🤖 网球发球分析机器人

发送视频给我，我会：
1. 上传视频到云端存储
2. 自动创建分析任务
3. 使用AI分析你的发球动作
4. 生成详细分析报告

支持的命令:
- help: 显示帮助
- status: 查看状态
- 查询 <任务ID>: 查询分析结果

分析内容包括：
✓ 五阶段动作分析
✓ NTRP等级评估
✓ 杨超教练专业建议
✓ 改进训练方案"""
        itchat.send(reply, msg['FromUserName'])
    
    elif text.lower() in ['status', '状态']:
        itchat.send("✅ 机器人运行正常\n📊 分析服务在线\n🎾 准备接收视频", msg['FromUserName'])
    
    elif text.startswith('查询') or text.startswith('查詢'):
        # 查询任务状态
        parts = text.split()
        if len(parts) >= 2:
            task_id = parts[1]
            status = query_task_status(task_id)
            
            if 'error' in status:
                reply = f"❌ 查询失败: {status['error']}"
            elif status.get('status') == 'success':
                result = status.get('result', {})
                reply = f"""✅ 分析完成！

📊 NTRP等级: {result.get('ntrp_level', 'N/A')}
🎯 置信度: {result.get('ntrp_confidence', 0):.1%}
📚 知识召回: {result.get('knowledge_recall_count', 0)}条
💾 样本入库: {'✅' if result.get('sample_saved') else '❌'}

发送 "详情 {task_id}" 查看完整报告"""
            elif status.get('status') == 'pending':
                reply = f"⏳ 任务正在排队中...\n任务ID: {task_id}"
            elif status.get('status') == 'running':
                reply = f"🔄 正在分析中...\n任务ID: {task_id}"
            elif status.get('status') in ('failed', 'low_quality'):
                reply = f"❌ 分析失败\n原因: {status.get('failure_reason', '未知错误')}"
            else:
                reply = f"📊 任务状态: {status.get('status', '未知')}\n任务ID: {task_id}"
            
            itchat.send(reply, msg['FromUserName'])
        else:
            itchat.send("❌ 请提供任务ID，例如: 查询 task-xxxx-xxxx", msg['FromUserName'])

if __name__ == '__main__':
    print("="*50)
    print("微信视频处理机器人")
    print("="*50)
    print("\n请扫描二维码登录微信...")
    print("登录成功后，发送视频给我即可自动上传至COS\n")
    
    # 登录微信
    itchat.auto_login(hotReload=True)
    
    print("\n✅ 登录成功！机器人正在运行...")
    print("请发送视频进行测试\n")
    
    # 运行机器人
    itchat.run()
