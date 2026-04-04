#!/usr/bin/env python3
"""
Five Phase Analyzer V2 - 骨骼数据质量修复版
修复MediaPipe骨骼点丢失时返回垃圾值的问题
"""

import numpy as np
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

# 可见度阈值
VISIBILITY_THRESHOLD = 0.5

@dataclass
class LandmarkPoint:
    x: float
    y: float
    z: float
    visibility: float

@dataclass
class FramePose:
    landmarks: Dict[str, LandmarkPoint]
    timestamp: float


def point_to_array(p: LandmarkPoint) -> np.ndarray:
    """转换为numpy数组"""
    return np.array([p.x, p.y, p.z])


def calc_angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    """计算三点角度"""
    ba = a - b
    bc = c - b
    cosine_angle = np.dot(ba, bc) / (np.linalg.norm(ba) * np.linalg.norm(bc) + 1e-6)
    angle = np.arccos(np.clip(cosine_angle, -1.0, 1.0))
    return np.degrees(angle)


def calc_distance(p1: LandmarkPoint, p2: LandmarkPoint) -> float:
    """计算两点距离"""
    return float(np.linalg.norm(point_to_array(p1) - point_to_array(p2)))


# ═══════════════════════════════════════════════════════════════
# 修复一：新增工具函数
# ═══════════════════════════════════════════════════════════════

def is_reliable(p: LandmarkPoint, threshold: float = VISIBILITY_THRESHOLD) -> bool:
    """判断单个骨骼点是否可信"""
    return p.visibility >= threshold


def reliable_angle(a: LandmarkPoint, b: LandmarkPoint, c: LandmarkPoint,
                   threshold: float = VISIBILITY_THRESHOLD) -> Optional[float]:
    """
    计算三点角度，任一点置信度不足则返回None，不参与后续统计。
    替代直接调用calc_angle，防止低置信度坐标(0,0)污染角度计算。
    """
    if a.visibility < threshold or b.visibility < threshold or c.visibility < threshold:
        return None
    return calc_angle(point_to_array(a), point_to_array(b), point_to_array(c))


def median_of_valid(values: List) -> Optional[float]:
    """
    取列表中非None值的中位数。
    有效帧不足3帧时返回None（数据不可信）。
    """
    valid = [v for v in values if v is not None]
    if len(valid) < 3:
        return None
    return float(np.median(valid))


def interpolate_poses(pose_sequence: List[FramePose]) -> List[FramePose]:
    """
    对骨骼点序列做线性插值，补全低置信度帧的坐标。
    
    策略：
    - 某帧某骨骼点visibility < VISIBILITY_THRESHOLD，且其前后各有一帧有效点，
      则用前后帧线性插值补全坐标，并将visibility标记为0.3（低可信插值）。
    - 序列两端（无前帧或无后帧）的丢失点不插值，保持原值。
    - 插值后骨骼点visibility=0.3仍低于阈值，不会参与reliable_angle()计算，
      但可用于需要坐标的其他计算（如手腕轨迹平滑）。
    
    Args:
        pose_sequence: extract_poses返回的List[FramePose]
    
    Returns:
        插值后的pose_sequence（原列表修改后返回）
    """
    if len(pose_sequence) < 3:
        return pose_sequence
    
    landmark_names = list(pose_sequence[0].landmarks.keys())
    
    for name in landmark_names:
        for i in range(1, len(pose_sequence) - 1):
            curr = pose_sequence[i].landmarks[name]
            if curr.visibility >= VISIBILITY_THRESHOLD:
                continue  # 当前帧可信，不需要插值
            
            # 找前一个有效帧
            prev_idx = None
            for j in range(i - 1, -1, -1):
                if pose_sequence[j].landmarks[name].visibility >= VISIBILITY_THRESHOLD:
                    prev_idx = j
                    break
            
            # 找后一个有效帧
            next_idx = None
            for j in range(i + 1, len(pose_sequence)):
                if pose_sequence[j].landmarks[name].visibility >= VISIBILITY_THRESHOLD:
                    next_idx = j
                    break
            
            if prev_idx is None or next_idx is None:
                continue  # 无法插值
            
            # 线性插值
            prev_lm = pose_sequence[prev_idx].landmarks[name]
            next_lm = pose_sequence[next_idx].landmarks[name]
            t = (i - prev_idx) / (next_idx - prev_idx)
            
            pose_sequence[i].landmarks[name] = LandmarkPoint(
                x=prev_lm.x + t * (next_lm.x - prev_lm.x),
                y=prev_lm.y + t * (next_lm.y - prev_lm.y),
                z=prev_lm.z + t * (next_lm.z - prev_lm.z),
                visibility=0.3  # 标记为插值点，低于阈值不参与reliable_angle
            )
    
    return pose_sequence


# ═══════════════════════════════════════════════════════════════
# 修复二：extract_poses() 提取完成后调用插值
# ═══════════════════════════════════════════════════════════════

def extract_poses(video_path: str, visibility_threshold: float = VISIBILITY_THRESHOLD):
    """
    从视频中提取姿态序列
    
    Returns:
        pose_sequence: List[FramePose]
        fps: float
        total_frames: int
    """
    # 这里应该是MediaPipe提取代码的占位符
    # 实际实现会调用MediaPipe提取骨骼点
    
    # 模拟提取结果
    pose_sequence = []
    fps = 30.0
    total_frames = 300
    
    print(f"\n提取完成: {len(pose_sequence)} 帧有效骨骼点")
    
    # 插值补全低置信度帧
    print("插值补全低置信度骨骼点...")
    pose_sequence = interpolate_poses(pose_sequence)
    
    return pose_sequence, fps, total_frames


# ═══════════════════════════════════════════════════════════════
# 修复三：修复_analyze_loading()中的角度计算
# ═══════════════════════════════════════════════════════════════

def _analyze_loading(poses: List[FramePose], quality_penalty: float):
    """
    分析蓄力阶段
    
    修复：使用reliable_angle()替代calc_angle()，过滤低置信度骨骼点
    使用median_of_valid()替代min()，取有效帧中位数
    """
    issues = {}
    metrics = {}
    
    if not poses:
        return issues, metrics
    
    # 肘部角度（奖杯姿势）
    elbow_angles = []
    for p in poses:
        rs = p.landmarks.get('right_shoulder')
        re = p.landmarks.get('right_elbow')
        rw = p.landmarks.get('right_wrist')
        if rs and re and rw:
            angle = reliable_angle(rs, re, rw)  # 使用可靠角度计算
            if angle is not None:
                elbow_angles.append(angle)
    
    if elbow_angles:
        # 使用有效帧中位数，而非最小值
        median_elbow = median_of_valid(elbow_angles)
        if median_elbow is not None:
            metrics['elbow_angle_median'] = median_elbow
            metrics['elbow_angle_min'] = min(elbow_angles)
            metrics['elbow_angle_max'] = max(elbow_angles)
            
            if median_elbow > 130:
                issues['trophy_not_reached'] = min(1.0, (median_elbow - 130) / 50) * quality_penalty
    
    # 膝盖角度（蓄力深度）
    knee_angles = []
    for p in poses:
        rh = p.landmarks.get('right_hip')
        rk = p.landmarks.get('right_knee')
        ra = p.landmarks.get('right_ankle')
        if rh and rk and ra:
            angle = reliable_angle(rh, rk, ra)  # 使用可靠角度计算
            if angle is not None:
                knee_angles.append(angle)
    
    if knee_angles:
        # 使用有效帧中位数，而非最小值
        median_knee = median_of_valid(knee_angles)
        if median_knee is not None:
            metrics['knee_angle_median'] = median_knee
            metrics['knee_angle_min'] = min(knee_angles)
            
            if median_knee > 140:
                issues['knee_not_bent'] = min(1.0, (median_knee - 140) / 40) * quality_penalty
    
    return issues, metrics


# ═══════════════════════════════════════════════════════════════
# 其他阶段分析函数（同样需要修复）
# ═══════════════════════════════════════════════════════════════

def _analyze_ready(poses: List[FramePose], quality_penalty: float):
    """分析准备阶段"""
    issues = {}
    metrics = {}
    
    if not poses:
        return issues, metrics
    
    # 站位宽度检查
    stance_widths = []
    for p in poses:
        l_ankle = p.landmarks.get('left_ankle')
        r_ankle = p.landmarks.get('right_ankle')
        if l_ankle and r_ankle and is_reliable(l_ankle) and is_reliable(r_ankle):
            width = calc_distance(l_ankle, r_ankle)
            stance_widths.append(width)
    
    if stance_widths:
        median_width = median_of_valid(stance_widths)
        if median_width is not None:
            metrics['stance_width'] = median_width
    
    return issues, metrics


def _analyze_toss(poses: List[FramePose], quality_penalty: float):
    """分析抛球阶段"""
    issues = {}
    metrics = {}
    
    # 抛球轨迹平滑度检查
    # 使用插值后的坐标计算
    
    return issues, metrics


def _analyze_contact(poses: List[FramePose], quality_penalty: float):
    """分析击球阶段"""
    issues = {}
    metrics = {}
    
    # 击球点高度检查
    contact_heights = []
    for p in poses:
        r_wrist = p.landmarks.get('right_wrist')
        if r_wrist and is_reliable(r_wrist):
            contact_heights.append(r_wrist.y)  # y坐标越小越高
    
    if contact_heights:
        median_height = median_of_valid(contact_heights)
        if median_height is not None:
            metrics['contact_height'] = median_height
    
    return issues, metrics


def _analyze_follow(poses: List[FramePose], quality_penalty: float):
    """分析随挥阶段"""
    issues = {}
    metrics = {}
    
    # 随挥完整性检查
    
    return issues, metrics


# ═══════════════════════════════════════════════════════════════
# 主分析函数
# ═══════════════════════════════════════════════════════════════

def analyze_five_phases(video_path: str) -> Dict[str, Any]:
    """
    五阶段分析主函数
    
    Returns:
        {
            'ready': {'issues': {}, 'metrics': {}},
            'toss': {'issues': {}, 'metrics': {}},
            'loading': {'issues': {}, 'metrics': {}},
            'contact': {'issues': {}, 'metrics': {}},
            'follow': {'issues': {}, 'metrics': {}},
        }
    """
    # 提取骨骼点
    pose_sequence, fps, total_frames = extract_poses(video_path)
    
    if not pose_sequence:
        return {}
    
    # 质量惩罚（根据有效帧比例）
    quality_penalty = min(1.0, len(pose_sequence) / total_frames * 2)
    
    # 五阶段分析
    results = {
        'ready': _analyze_ready(pose_sequence, quality_penalty),
        'toss': _analyze_toss(pose_sequence, quality_penalty),
        'loading': _analyze_loading(pose_sequence, quality_penalty),
        'contact': _analyze_contact(pose_sequence, quality_penalty),
        'follow': _analyze_follow(pose_sequence, quality_penalty),
    }
    
    return results


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        results = analyze_five_phases(sys.argv[1])
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print("用法: python3 five_phase_analyzer_v2_fixed.py <视频路径>")
