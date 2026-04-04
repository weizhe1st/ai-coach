#!/usr/bin/env python3
"""
MediaPipe 辅助分析模块 v2.0
提取量化指标供 Kimi Vision 分析参考。

修复记录（v1 → v2）：
- 修复 os/json 未导入
- 修复 stance_width KeyError
- 修复 detect_for_video timestamp 单位（帧序号 → 毫秒）
- 加入置信度过滤，低可信骨骼点不参与角度计算
- min()/max() 改为对有效值取中位数（更鲁棒）
- 新增 data_quality 字段，标注每个指标的有效帧覆盖率
"""

import os
import cv2
import json
import numpy as np

VISIBILITY_THRESHOLD = 0.5  # 骨骼点置信度阈值，低于此值不参与计算
SAMPLE_EVERY = 3  # 每 N 帧采样一次


def calculate_angle(p1, p2, p3) -> float:
    """计算三点形成的角度（度）"""
    a = np.array([p1.x, p1.y])
    b = np.array([p2.x, p2.y])
    c = np.array([p3.x, p3.y])
    ba = a - b
    bc = c - b
    norm = np.linalg.norm(ba) * np.linalg.norm(bc)
    if norm < 1e-8:
        return 0.0
    cosine = np.dot(ba, bc) / norm
    return float(np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0))))


def is_reliable(lm, threshold: float = VISIBILITY_THRESHOLD) -> bool:
    """判断骨骼点是否可信"""
    return hasattr(lm, 'visibility') and lm.visibility >= threshold


def median_valid(values: list):
    """取列表中有效值（非 None）的中位数，不足3个返回 None"""
    valid = [v for v in values if v is not None]
    if len(valid) < 3:
        return None
    return float(np.median(valid))


def extract_pose_metrics(video_path: str) -> dict:
    """
    从视频中提取姿态量化指标。
    
    Returns:
        dict: 量化指标 + 数据质量信息。
        MediaPipe 不可用或视频无法打开时返回 None。
    """
    try:
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions
    except ImportError:
        print("[MediaPipe] 未安装，跳过量化分析")
        return None
    
    model_path = '/tmp/pose_landmarker.task'
    if not os.path.exists(model_path):
        print(f"[MediaPipe] 模型文件不存在: {model_path}")
        return None
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[MediaPipe] 无法打开视频: {video_path}")
        return None
    
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    
    base_options = BaseOptions(model_asset_path=model_path)
    options = vision.PoseLandmarkerOptions(
        base_options=base_options,
        running_mode=vision.RunningMode.VIDEO,
        num_poses=1,
        min_pose_detection_confidence=0.5,
        min_pose_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    detector = vision.PoseLandmarker.create_from_options(options)
    
    # 原始数据列表（每帧一个值或 None）
    raw = {
        'knee_angles': [],      # 右髋-膝-踝
        'elbow_angles': [],     # 右肩-肘-腕
        'wrist_heights': [],    # 右腕 y 坐标（越小越高）
        'stance_widths': [],    # 双踝水平距离
        'shoulder_rotations': [],  # 双肩连线角度（相对水平）
    }
    
    frame_count = 0
    total_sampled = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        if frame_count % SAMPLE_EVERY != 0:
            continue
        
        total_sampled += 1
        timestamp_ms = int((frame_count / fps) * 1000)  # 修复：使用毫秒
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        results = detector.detect_for_video(mp_image, timestamp_ms)
        
        if not results.pose_landmarks:
            # 未检测到人体，所有指标本帧为 None
            for key in raw:
                raw[key].append(None)
            continue
        
        lm = results.pose_landmarks[0]
        
        # 膝盖角度：右髋(24) - 右膝(26) - 右踝(28)
        if is_reliable(lm[24]) and is_reliable(lm[26]) and is_reliable(lm[28]):
            raw['knee_angles'].append(calculate_angle(lm[24], lm[26], lm[28]))
        else:
            raw['knee_angles'].append(None)
        
        # 肘部角度：右肩(12) - 右肘(14) - 右腕(16)
        if is_reliable(lm[12]) and is_reliable(lm[14]) and is_reliable(lm[16]):
            raw['elbow_angles'].append(calculate_angle(lm[12], lm[14], lm[16]))
        else:
            raw['elbow_angles'].append(None)
        
        # 右腕高度：y 值越小越高，转换为"高度比"（1-y）
        if is_reliable(lm[16]):
            raw['wrist_heights'].append(1.0 - lm[16].y)
        else:
            raw['wrist_heights'].append(None)
        
        # 站位宽度：左踝(27) - 右踝(28) 水平距离
        if is_reliable(lm[27]) and is_reliable(lm[28]):
            raw['stance_widths'].append(abs(lm[27].x - lm[28].x))
        else:
            raw['stance_widths'].append(None)
        
        # 肩膀旋转角度：双肩连线相对水平线的角度
        if is_reliable(lm[11]) and is_reliable(lm[12]):
            dx = lm[12].x - lm[11].x
            dy = lm[12].y - lm[11].y
            raw['shoulder_rotations'].append(float(np.degrees(np.arctan2(dy, dx))))
        else:
            raw['shoulder_rotations'].append(None)
    
    cap.release()
    detector.close()
    
    # 聚合：对有效值取中位数（更鲁棒）
    metrics = {
        'min_knee_angle': median_valid(raw['knee_angles']),
        'max_elbow_angle': median_valid(raw['elbow_angles']),
        'max_wrist_height': median_valid(raw['wrist_heights']),
        'median_stance_width': median_valid(raw['stance_widths']),
        'shoulder_rotation': median_valid(raw['shoulder_rotations']),
    }
    
    # 数据质量：有效帧覆盖率
    data_quality = {
        'total_sampled': total_sampled,
        'knee_angle_coverage': len([v for v in raw['knee_angles'] if v is not None]) / max(1, total_sampled),
        'elbow_angle_coverage': len([v for v in raw['elbow_angles'] if v is not None]) / max(1, total_sampled),
        'wrist_height_coverage': len([v for v in raw['wrist_heights'] if v is not None]) / max(1, total_sampled),
        'stance_width_coverage': len([v for v in raw['stance_widths'] if v is not None]) / max(1, total_sampled),
        'shoulder_rotation_coverage': len([v for v in raw['shoulder_rotations'] if v is not None]) / max(1, total_sampled),
    }
    
    return {
        'metrics': metrics,
        'data_quality': data_quality,
        'raw_samples': total_sampled,
    }


MEDIAPIPE_ENABLED = True  # 控制开关，False则跳过MediaPipe

def format_for_kimi(metrics: dict, data_quality: dict) -> str:
    """
    将MediaPipe指标格式化为Kimi可读的辅助文字
    
    策略：
    - 覆盖率低于50%的指标不输出数字，写"数据不足"
    - 同时输出数字和辅助解读（如"膝盖轻微弯曲，蓄力不足"）
    """
    lines = []
    lines.append("【MediaPipe量化指标参考（辅助）】")
    
    # 膝盖角度
    knee = metrics.get('min_knee_angle')
    knee_coverage = data_quality.get('knee_angle_coverage', 0)
    if knee_coverage < 0.5 or knee is None:
        lines.append("- 膝盖角度：数据不足，请依赖视觉观察")
    else:
        if knee < 100:
            desc = "膝盖深度弯曲，蓄力充分（约4.5+级水平）"
        elif knee < 120:
            desc = "膝盖明显弯曲，蓄力良好（约4.0级水平）"
        elif knee < 140:
            desc = "膝盖轻微弯曲，蓄力一般（约3.5级水平）"
        else:
            desc = "膝盖蓄力不足（约3.0级或以下）"
        lines.append(f"- 膝盖最小角度：{knee:.1f}°，{desc}")
    
    # 肘部角度
    elbow = metrics.get('max_elbow_angle')
    elbow_coverage = data_quality.get('elbow_angle_coverage', 0)
    if elbow_coverage < 0.5 or elbow is None:
        lines.append("- 肘部角度：数据不足，请依赖视觉观察")
    else:
        if elbow > 170:
            desc = "肘部充分伸直，奖杯姿势到位"
        elif elbow > 150:
            desc = "肘部基本伸直，奖杯姿势尚可"
        else:
            desc = "肘部弯曲明显，奖杯姿势不足"
        lines.append(f"- 肘部最大角度：{elbow:.1f}°，{desc}")
    
    # 击球点高度
    wrist = metrics.get('max_wrist_height')
    wrist_coverage = data_quality.get('wrist_height_coverage', 0)
    if wrist_coverage < 0.5 or wrist is None:
        lines.append("- 击球点高度：数据不足，请依赖视觉观察")
    else:
        if wrist > 0.8:
            desc = "击球点极高，充分利用身高优势"
        elif wrist > 0.6:
            desc = "击球点适中"
        else:
            desc = "击球点偏低"
        lines.append(f"- 击球点高度比：{wrist:.2f}，{desc}")
    
    # 数据质量总结
    lines.append(f"\n【数据质量】有效帧覆盖率：{data_quality.get('total_sampled', 0)}帧采样")
    
    return '\n'.join(lines)

def enhance_vision_result_with_mediapipe(vision_result: dict, mp_result: dict) -> dict:
    """
    将 MediaPipe 量化指标整合到 Vision 分析结果中
    
    Args:
        vision_result: Kimi Vision 分析结果
        mp_result: MediaPipe 提取的量化指标
    
    Returns:
        增强后的结果
    """
    if not mp_result or 'metrics' not in mp_result:
        return vision_result
    
    metrics = mp_result['metrics']
    data_quality = mp_result.get('data_quality', {})
    
    # 添加量化指标
    vision_result['quantitative_metrics'] = metrics
    vision_result['data_quality'] = data_quality
    
    # 根据量化指标验证/修正评级
    ntrp_level = vision_result.get('ntrp_level', '3.0')
    
    # 膝盖角度验证
    knee_angle = metrics.get('min_knee_angle')
    if knee_angle is not None:
        # 根据膝盖角度推断实际等级
        if knee_angle < 100:
            inferred_level = '4.5+'
        elif knee_angle < 120:
            inferred_level = '4.0'
        elif knee_angle < 140:
            inferred_level = '3.5'
        else:
            inferred_level = '3.0'
        
        # 如果 Vision 评级与量化指标差距大，添加提示
        vision_level_num = float(ntrp_level.replace('+', ''))
        inferred_level_num = float(inferred_level.replace('+', ''))
        
        if abs(vision_level_num - inferred_level_num) > 0.5:
            if '_mp_comparison' not in vision_result:
                vision_result['_mp_comparison'] = {}
            vision_result['_mp_comparison']['knee_level_discrepancy'] = {
                'vision_level': ntrp_level,
                'knee_inferred_level': inferred_level,
                'knee_angle': knee_angle,
                'note': f'膝盖角度{knee_angle:.1f}°对应{inferred_level}级，与Vision评级{ntrp_level}有差异'
            }
    
    return vision_result


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        result = extract_pose_metrics(sys.argv[1])
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print("用法: python3 mediapipe_helper.py <视频路径>")
