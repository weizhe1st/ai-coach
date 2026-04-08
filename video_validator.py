#!/usr/bin/env python3
"""
视频校验器 - 校验本地视频文件的有效性
"""

import os
from typing import Dict, Any

# 允许的视频扩展名
ALLOWED_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv', '.webm']

# 最大文件大小（500MB）
MAX_FILE_SIZE = 500 * 1024 * 1024

# 最小文件大小（1KB）
MIN_FILE_SIZE = 1024


def validate_video_file(filepath: str) -> Dict[str, Any]:
    """
    校验视频文件
    
    Args:
        filepath: 文件路径
    
    Returns:
        校验结果字典
    """
    result = {
        "valid": False,
        "file_size": 0,
        "extension": None,
        "error_code": None,
        "error_message": None
    }
    
    # 1. 检查文件是否存在
    if not filepath:
        result["error_code"] = "FILE_NOT_SPECIFIED"
        result["error_message"] = "文件路径未指定"
        return result
    
    if not os.path.exists(filepath):
        result["error_code"] = "FILE_NOT_FOUND"
        result["error_message"] = f"文件不存在: {filepath}"
        return result
    
    # 2. 检查是否是文件
    if not os.path.isfile(filepath):
        result["error_code"] = "NOT_A_FILE"
        result["error_message"] = "路径不是文件"
        return result
    
    # 3. 检查文件大小
    try:
        file_size = os.path.getsize(filepath)
        result["file_size"] = file_size
        
        if file_size == 0:
            result["error_code"] = "FILE_EMPTY"
            result["error_message"] = "文件大小为0"
            return result
        
        if file_size < MIN_FILE_SIZE:
            result["error_code"] = "FILE_TOO_SMALL"
            result["error_message"] = f"文件太小 ({file_size} bytes)，可能不是有效视频"
            return result
        
        if file_size > MAX_FILE_SIZE:
            result["error_code"] = "FILE_TOO_LARGE"
            result["error_message"] = f"文件太大 ({file_size / 1024 / 1024:.1f} MB)，超过限制 {MAX_FILE_SIZE / 1024 / 1024} MB"
            return result
            
    except Exception as e:
        result["error_code"] = "SIZE_CHECK_ERROR"
        result["error_message"] = f"检查文件大小失败: {e}"
        return result
    
    # 4. 检查文件扩展名
    try:
        ext = os.path.splitext(filepath)[1].lower()
        result["extension"] = ext
        
        if ext not in ALLOWED_EXTENSIONS:
            result["error_code"] = "INVALID_EXTENSION"
            result["error_message"] = f"不支持的文件扩展名: {ext}，允许的扩展名: {ALLOWED_EXTENSIONS}"
            return result
            
    except Exception as e:
        result["error_code"] = "EXTENSION_CHECK_ERROR"
        result["error_message"] = f"检查扩展名失败: {e}"
        return result
    
    # 5. 检查文件是否可读
    try:
        with open(filepath, 'rb') as f:
            # 尝试读取前几个字节
            header = f.read(8)
            if len(header) < 8:
                result["error_code"] = "FILE_UNREADABLE"
                result["error_message"] = "文件无法读取或内容不完整"
                return result
    except Exception as e:
        result["error_code"] = "FILE_UNREADABLE"
        result["error_message"] = f"文件无法读取: {e}"
        return result
    
    # 全部通过
    result["valid"] = True
    return result


def get_video_info(filepath: str) -> Dict[str, Any]:
    """
    获取视频基本信息（简化版，后续可扩展）
    
    Args:
        filepath: 文件路径
    
    Returns:
        视频信息字典
    """
    info = {
        "filepath": filepath,
        "exists": os.path.exists(filepath),
        "size": 0,
        "extension": None
    }
    
    if info["exists"]:
        info["size"] = os.path.getsize(filepath)
        info["extension"] = os.path.splitext(filepath)[1].lower()
    
    return info


if __name__ == '__main__':
    # 测试
    import tempfile
    
    print("[VideoValidator] 测试")
    
    # 测试不存在的文件
    result = validate_video_file("/path/to/nonexistent.mp4")
    print(f"不存在的文件: {result}")
    
    # 测试空文件
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
        empty_file = f.name
    result = validate_video_file(empty_file)
    print(f"空文件: {result}")
    os.unlink(empty_file)
    
    # 测试有效文件
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
        f.write(b"fake video content for testing purpose")
        valid_file = f.name
    result = validate_video_file(valid_file)
    print(f"有效文件: {result}")
    os.unlink(valid_file)
    
    print("测试完成")
