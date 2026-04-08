#!/usr/bin/env python3
"""
微信消息处理器 - 接收用户上传的视频并返回分析报告
"""

import os
import sys
import json
import tempfile
from pathlib import Path

# 导入分析服务
sys.path.insert(0, '/data/apps/xiaolongxia')
from complete_analysis_service import analyze_video_complete

def download_video_streaming(video_url, output_path, max_size_mb=100):
    """
    流式下载视频，避免大文件占用内存
    
    Args:
        video_url: 视频URL
        output_path: 输出文件路径
        max_size_mb: 最大文件大小(MB)
    
    Returns:
        (bool, str): (是否成功, 消息)
    """
    import requests
    
    try:
        print(f"[下载] 开始下载: {video_url[:60]}...")
        
        # 设置 headers
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0'
        }
        
        response = requests.get(video_url, headers=headers, stream=True, timeout=60)
        print(f"[下载] HTTP状态码: {response.status_code}")
        
        if response.status_code != 200:
            return False, f"HTTP错误: {response.status_code}"
        
        # 检查Content-Length
        content_length = response.headers.get('Content-Length')
        if content_length:
            size_mb = int(content_length) / (1024 * 1024)
            print(f"[下载] 文件大小: {size_mb:.2f} MB")
            if size_mb > max_size_mb:
                return False, f"视频过大 ({size_mb:.1f}MB)"
        
        # 流式写入文件
        downloaded_size = 0
        max_size_bytes = max_size_mb * 1024 * 1024
        
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    downloaded_size += len(chunk)
                    if downloaded_size > max_size_bytes:
                        return False, f"视频过大，超过{max_size_mb}MB限制"
                    f.write(chunk)
        
        # 验证文件
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            print(f"[下载] 成功: {output_path}, 大小: {file_size/1024:.2f}KB")
            return True, "下载成功"
        else:
            return False, "文件未创建"
        
    except requests.exceptions.Timeout:
        return False, "下载超时"
    except requests.exceptions.ConnectionError:
        return False, "连接失败"
    except Exception as e:
        print(f"[下载] 错误: {e}")
        import traceback
        traceback.print_exc()
        return False, f"下载失败: {str(e)}"


def handle_weixin_message(message_data):
    """
    处理微信消息
    
    Args:
        message_data: 微信消息数据
        
    Returns:
        str: 回复消息
    """
    msg_type = message_data.get('MsgType', '')
    user_id = message_data.get('FromUserName', '')
    
    # 处理视频消息
    if msg_type == 'video':
        video_url = message_data.get('VideoUrl', '')
        
        if not video_url:
            return "❌ 无法获取视频，请重新上传"
        
        # 即时确认前缀（同步模式下拼在结果前面，让用户知道系统收到了）
        WAITING_PREFIX = "🎾 收到！正在分析你的发球视频，请稍候…\n（通常需要30-60秒）\n\n"
        
        # 检查是否是本地文件路径（测试模式）
        if video_url.startswith('file://'):
            # 本地文件直接分析
            video_path = video_url[7:]  # 去掉 file:// 前缀
            if not os.path.exists(video_path):
                return WAITING_PREFIX + "❌ 本地视频文件不存在"
            
            result = analyze_video_complete(video_path, user_id)
            if result.get('success'):
                return WAITING_PREFIX + "─" * 20 + "\n" + result.get('report', '分析完成，但报告生成失败')
            else:
                return WAITING_PREFIX + result.get('report', result.get('error', '分析失败'))
        
        # 下载视频（流式）
        video_path = None
        need_cleanup = False
        try:
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
                video_path = f.name
                need_cleanup = True
            
            success, msg = download_video_streaming(video_url, video_path)
            if not success:
                return WAITING_PREFIX + f"❌ {msg}"
            
            # 分析视频（完整版）
            result = analyze_video_complete(video_path, user_id)
            
            if result['success']:
                # 分析成功：在报告前加确认前缀
                return WAITING_PREFIX + "─" * 20 + "\n" + result.get('report', '分析完成')
            else:
                return WAITING_PREFIX + result.get('report', result.get('error', '分析失败'))
                
        except Exception as e:
            return WAITING_PREFIX + f"❌ 分析过程出错，请稍后重新发送视频\n错误信息：{str(e)}"
        finally:
            # 清理临时文件
            if need_cleanup and video_path and os.path.exists(video_path):
                try:
                    os.unlink(video_path)
                except Exception:
                    pass
    
    # 处理文本消息
    elif msg_type == 'text':
        content = message_data.get('Content', '').strip()
        
        if content in ['帮助', 'help', '?']:
            return """🎾 网球发球分析助手

发送视频给我，我将为你分析发球技术！

📸 拍摄建议：
• 侧面或背面角度
• 光线充足
• 包含完整发球动作
• 时长5-60秒

📊 分析内容：
• NTRP等级评估
• 五阶段技术分析
• 个性化训练建议

开始上传你的发球视频吧！"""
        
        return "请上传你的网球发球视频，我将为你分析技术动作！"
    
    # 其他消息类型
    else:
        return "请上传视频文件，目前仅支持视频分析"

# 命令行测试入口
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', help='测试视频路径')
    parser.add_argument('--user-id', default='test_user', help='用户ID')
    
    args = parser.parse_args()
    
    if args.video:
        # 直接分析本地视频
        result = analyze_video_complete(args.video, args.user_id)
        print(result['report'])
    else:
        print("用法: python3 weixin_handler.py --video <视频路径>")
