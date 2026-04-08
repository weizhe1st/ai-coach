#!/usr/bin/env python3
"""
complete_analysis_service_patch.py - 为现有服务添加 normalizer 支持
在文件末尾添加标准化处理
"""

import sys
sys.path.insert(0, '/data/apps/xiaolongxia')

# 导入 normalizer
from analysis_normalizer import normalize_analysis_result

# 保存原始函数的引用
import complete_analysis_service as cas

# 保存原始函数
_original_analyze_video_complete = cas.analyze_video_complete

def analyze_video_complete_with_normalizer(video_path, user_id=None, task_id=None):
    """
    包装原始分析函数，添加结果标准化
    """
    # 调用原始分析
    result = _original_analyze_video_complete(video_path, user_id, task_id)
    
    if not result.get('success'):
        return result
    
    # 获取原始分析结果
    raw_result = result.get('analysis_result', {})
    
    # 标准化结果
    model_meta = {
        "provider": "moonshot" if cas.MODEL_PROVIDER != 'qwen' else 'aliyun',
        "model": MODEL_NAME,
        "latency_ms": 0  # 可以后续补充
    }
    
    normalization = normalize_analysis_result(raw_result, model_meta)
    normalized_result = normalization['normalized_result']
    
    # 将标准化结果添加到返回中
    result['normalized_result'] = normalized_result
    result['normalization_warnings'] = normalization['warnings']
    result['normalization_mapping'] = normalization['mapping_trace']
    
    # 更新报告使用标准化结果
    if normalized_result.get('report_text'):
        result['report'] = normalized_result['report_text']
    
    return result

# 替换原始函数
cas.analyze_video_complete = analyze_video_complete_with_normalizer

# 保持原始函数名可用
cas.analyze_video_complete_original = _original_analyze_video_complete

print("[Patch] complete_analysis_service 已添加 normalizer 支持")
