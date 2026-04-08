#!/usr/bin/env python3
"""
视频拉取器 - 统一视频输入层
支持多种来源：wechat_temp_url, cos_url, local_file
"""

import os
import sys
import requests
import shutil
from typing import Dict, Any, Optional
from pathlib import Path

sys.path.insert(0, '/data/apps/xiaolongxia')

from temp_file_manager import make_temp_video_path, cleanup_temp_file
from video_validator import validate_video_file

# 支持的来源类型
SUPPORTED_SOURCE_TYPES = [
    'wechat_temp_url',
    'cos_url',
    'local_file'
]

# 下载超时（秒）
DOWNLOAD_TIMEOUT = 120

# 流式下载块大小（字节）
CHUNK_SIZE = 8192


def fetch_video_to_local(source_type: str, source_url: str, task_id: str = None) -> Dict[str, Any]:
    """
    统一视频拉取入口
    
    Args:
        source_type: 来源类型 (wechat_temp_url, cos_url, local_file)
        source_url: 来源URL或路径
        task_id: 任务ID（用于生成临时文件名）
    
    Returns:
        结果字典，包含：
        - success: 是否成功
        - local_video_path: 本地文件路径（成功时）
        - file_size: 文件大小
        - content_type: 内容类型
        - error_code: 错误码（失败时）
        - error_message: 错误信息（失败时）
    """
    result = {
        "success": False,
        "local_video_path": None,
        "file_size": 0,
        "content_type": None,
        "error_code": None,
        "error_message": None
    }
    
    print(f"[VideoFetcher] 开始拉取视频: type={source_type}, task={task_id}")
    
    # 1. 校验来源类型
    if source_type not in SUPPORTED_SOURCE_TYPES:
        result["error_code"] = "UNSUPPORTED_SOURCE_TYPE"
        result["error_message"] = f"不支持的来源类型: {source_type}，支持的类型: {SUPPORTED_SOURCE_TYPES}"
        print(f"[VideoFetcher] ❌ {result['error_message']}")
        return result
    
    # 2. 根据来源类型路由处理
    try:
        if source_type == 'wechat_temp_url':
            fetch_result = _fetch_from_url(source_url, task_id, 'wechat')
        elif source_type == 'cos_url':
            fetch_result = _fetch_from_url(source_url, task_id, 'cos')
        elif source_type == 'local_file':
            fetch_result = _fetch_from_local(source_url, task_id)
        else:
            # 理论上不会走到这里
            fetch_result = {
                "success": False,
                "local_video_path": None,
                "error_code": "UNKNOWN_ERROR",
                "error_message": "未知错误"
            }
        
        # 3. 如果拉取成功，进行视频校验
        if fetch_result["success"]:
            local_path = fetch_result["local_video_path"]
            validation = validate_video_file(local_path)
            
            if validation["valid"]:
                result["success"] = True
                result["local_video_path"] = local_path
                result["file_size"] = validation["file_size"]
                result["content_type"] = fetch_result.get("content_type")
                print(f"[VideoFetcher] ✅ 视频拉取并校验成功: {local_path}, size={result['file_size']}")
            else:
                # 校验失败，清理临时文件
                cleanup_temp_file(local_path)
                result["error_code"] = validation["error_code"]
                result["error_message"] = validation["error_message"]
                print(f"[VideoFetcher] ❌ 视频校验失败: {result['error_message']}")
        else:
            result["error_code"] = fetch_result["error_code"]
            result["error_message"] = fetch_result["error_message"]
            print(f"[VideoFetcher] ❌ 视频拉取失败: {result['error_message']}")
            
    except Exception as e:
        result["error_code"] = "FETCH_EXCEPTION"
        result["error_message"] = f"拉取过程异常: {str(e)}"
        print(f"[VideoFetcher] ❌ 拉取异常: {e}")
    
    return result


def _fetch_from_url(url: str, task_id: str, source_name: str) -> Dict[str, Any]:
    """
    从URL下载视频（流式下载）
    
    Args:
        url: 视频URL
        task_id: 任务ID
        source_name: 来源名称（用于日志）
    
    Returns:
        结果字典
    """
    result = {
        "success": False,
        "local_video_path": None,
        "content_type": None,
        "error_code": None,
        "error_message": None
    }
    
    print(f"[VideoFetcher] 从 {source_name} 下载: {url[:60]}...")
    
    try:
        # 流式下载
        response = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
        response.raise_for_status()
        
        # 获取内容类型
        content_type = response.headers.get('Content-Type', 'unknown')
        result["content_type"] = content_type
        
        # 生成临时文件路径
        temp_path = make_temp_video_path(task_id or "unknown", ".mp4")
        
        # 流式写入文件
        downloaded_size = 0
        with open(temp_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
                    downloaded_size += len(chunk)
        
        result["success"] = True
        result["local_video_path"] = temp_path
        print(f"[VideoFetcher] 下载完成: {temp_path}, size={downloaded_size}")
        
    except requests.exceptions.Timeout:
        result["error_code"] = "DOWNLOAD_TIMEOUT"
        result["error_message"] = f"下载超时（{DOWNLOAD_TIMEOUT}秒）"
    except requests.exceptions.ConnectionError as e:
        result["error_code"] = "CONNECTION_ERROR"
        result["error_message"] = f"连接错误: {str(e)}"
    except requests.exceptions.HTTPError as e:
        result["error_code"] = f"HTTP_{e.response.status_code}"
        result["error_message"] = f"HTTP错误: {e.response.status_code}"
    except Exception as e:
        result["error_code"] = "DOWNLOAD_ERROR"
        result["error_message"] = f"下载失败: {str(e)}"
    
    return result


def _fetch_from_local(local_path: str, task_id: str) -> Dict[str, Any]:
    """
    从本地文件获取
    
    Args:
        local_path: 本地文件路径
        task_id: 任务ID
    
    Returns:
        结果字典
    """
    result = {
        "success": False,
        "local_video_path": None,
        "content_type": None,
        "error_code": None,
        "error_message": None
    }
    
    print(f"[VideoFetcher] 从本地获取: {local_path}")
    
    try:
        # 检查源文件
        if not os.path.exists(local_path):
            result["error_code"] = "LOCAL_FILE_NOT_FOUND"
            result["error_message"] = f"本地文件不存在: {local_path}"
            return result
        
        if not os.path.isfile(local_path):
            result["error_code"] = "LOCAL_PATH_NOT_FILE"
            result["error_message"] = f"本地路径不是文件: {local_path}"
            return result
        
        # 复制到临时目录（保持隔离性）
        temp_path = make_temp_video_path(task_id or "unknown", 
                                        os.path.splitext(local_path)[1])
        shutil.copy2(local_path, temp_path)
        
        result["success"] = True
        result["local_video_path"] = temp_path
        result["content_type"] = "video/local"
        print(f"[VideoFetcher] 本地文件复制完成: {temp_path}")
        
    except Exception as e:
        result["error_code"] = "LOCAL_COPY_ERROR"
        result["error_message"] = f"复制本地文件失败: {str(e)}"
    
    return result


def cleanup_fetched_video(local_path: str):
    """
    清理已拉取的视频文件
    
    Args:
        local_path: 本地文件路径
    """
    cleanup_temp_file(local_path)


if __name__ == '__main__':
    # 测试
    print("[VideoFetcher] 测试")
    
    # 测试不支持的来源类型
    result = fetch_video_to_local("unsupported_type", "http://test.com/video.mp4", "task_test_001")
    print(f"不支持的类型: success={result['success']}, error={result['error_code']}")
    
    # 测试本地文件（创建临时文件）
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
        f.write(b"fake video content for testing")
        test_file = f.name
    
    result = fetch_video_to_local("local_file", test_file, "task_test_002")
    print(f"本地文件: success={result['success']}, path={result['local_video_path']}, size={result['file_size']}")
    
    # 清理
    if result['local_video_path']:
        cleanup_fetched_video(result['local_video_path'])
    os.unlink(test_file)
    
    print("测试完成")
