#!/usr/bin/env python3
"""
临时文件管理器 - 统一管理视频临时文件
"""

import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime

# 临时文件根目录
TEMP_ROOT = os.environ.get('TEMP_VIDEO_ROOT', '/tmp/video_analysis')


def ensure_temp_dir():
    """确保临时目录存在"""
    os.makedirs(TEMP_ROOT, exist_ok=True)
    return TEMP_ROOT


def make_temp_video_path(task_id: str, suffix: str = ".mp4") -> str:
    """
    生成临时视频文件路径
    
    Args:
        task_id: 任务ID
        suffix: 文件后缀
    
    Returns:
        临时文件完整路径
    """
    ensure_temp_dir()
    
    # 使用时间戳+task_id的一部分生成唯一文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_task_id = task_id.replace("/", "_").replace("\\", "_")[:20]
    filename = f"{timestamp}_{safe_task_id}{suffix}"
    
    filepath = os.path.join(TEMP_ROOT, filename)
    return filepath


def cleanup_temp_file(filepath: str):
    """
    清理临时文件
    
    Args:
        filepath: 文件路径
    """
    try:
        if filepath and os.path.exists(filepath):
            os.unlink(filepath)
            print(f"[TempFileManager] 临时文件已清理: {filepath}")
    except Exception as e:
        print(f"[TempFileManager] 清理临时文件失败: {filepath}, 错误: {e}")


def cleanup_old_temp_files(max_age_hours: int = 24):
    """
    清理超过指定时间的临时文件
    
    Args:
        max_age_hours: 最大保留时间（小时）
    """
    try:
        if not os.path.exists(TEMP_ROOT):
            return
        
        now = datetime.now().timestamp()
        max_age_seconds = max_age_hours * 3600
        
        count = 0
        for filename in os.listdir(TEMP_ROOT):
            filepath = os.path.join(TEMP_ROOT, filename)
            if os.path.isfile(filepath):
                file_age = now - os.path.getmtime(filepath)
                if file_age > max_age_seconds:
                    os.unlink(filepath)
                    count += 1
        
        if count > 0:
            print(f"[TempFileManager] 清理了 {count} 个过期临时文件")
            
    except Exception as e:
        print(f"[TempFileManager] 清理过期文件失败: {e}")


def get_temp_file_size(filepath: str) -> int:
    """获取临时文件大小"""
    try:
        return os.path.getsize(filepath)
    except:
        return 0


if __name__ == '__main__':
    # 测试
    print("[TempFileManager] 测试")
    
    # 生成路径
    path = make_temp_video_path("task_test_001")
    print(f"生成路径: {path}")
    
    # 创建空文件
    with open(path, 'w') as f:
        f.write("test")
    
    print(f"文件大小: {get_temp_file_size(path)}")
    
    # 清理
    cleanup_temp_file(path)
    
    print("测试完成")
