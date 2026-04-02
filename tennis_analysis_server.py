#!/usr/bin/env python3
"""
五阶段网球发球分析服务
部署为HTTP API服务器，接收视频文件并返回五阶段分析结果
"""

import os
import sys
import json
import tempfile
import shutil
from datetime import datetime
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import cv2
import numpy as np
import urllib.request
import urllib.error

# 导入MediaPipe
try:
    import mediapipe as mp
    from mediapipe.tasks.python import vision
    from mediapipe.tasks.python.core.base_options import BaseOptions
    MEDIAPIPE_AVAILABLE = True
except ImportError as e:
    print(f"MediaPipe导入错误: {e}")
    MEDIAPIPE_AVAILABLE = False

app = Flask(__name__)

# 配置
UPLOAD_FOLDER = '/tmp/tennis_analysis_uploads'
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}
MODEL_PATH = '/tmp/pose_landmarker.task'
# 统一知识库（3位教练融合版：杨超 + 赵凌曦 + fuzzy_yellow）
KNOWLEDGE_BASE_URL = 'https://tennis-ai-1411340868.cos.ap-shanghai.myqcloud.com/coaches/unified_knowledge_base/merged/unified_knowledge_v3.json'

# COS 配置
COS_BUCKET = 'tennis-ai-1411340868'
COS_REGION = 'ap-shanghai'
COS_BASE_URL = f'https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com'

# 数据库配置
DB_PATH = '/data/db/xiaolongxia_learning.db'

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 知识库缓存
_knowledge_base_cache = None
_knowledge_base_loaded = False

# 系统配置
SYSTEM_CONFIG = {
    "fps": 30,
    "real_time": False,
    "target_response_time": 30,
    "normalization": "shoulder_width",
    "ball_tracking": False,
    "hand_model": False,
    "confidence_output": True,
}

# 从 level_model_service.py 导入多维度等级评估模型
LEVEL_MODELS = {
    '2.0': {
        'name': '入门级',
        'score_range': (0, 40),
        'key_features': {
            'max_elbow_angle': (90, 140),
            'min_knee_angle': (120, 150),
            'stance_width': (0.5, 1.5)
        }
    },
    '3.0': {
        'name': '进阶级',
        'score_range': (40, 60),
        'key_features': {
            'max_elbow_angle': (140, 160),
            'min_knee_angle': (100, 120),
            'stance_width': (1.5, 2.5)
        }
    },
    '4.0': {
        'name': '熟练级',
        'score_range': (60, 80),
        'key_features': {
            'max_elbow_angle': (160, 170),
            'min_knee_angle': (80, 100),
            'stance_width': (2.0, 3.0)
        }
    },
    '5.0': {
        'name': '精通级',
        'score_range': (80, 95),
        'key_features': {
            'max_elbow_angle': (170, 180),
            'min_knee_angle': (60, 80),
            'stance_width': (2.5, 3.5)
        }
    },
    '5.0+': {
        'name': '专业级',
        'score_range': (95, 100),
        'key_features': {
            'max_elbow_angle': (175, 180),
            'min_knee_angle': (50, 70),
            'stance_width': (2.5, 4.0)
        }
    }
}

# 特征权重 - 不是所有指标同等重要
FEATURE_WEIGHTS = {
    'max_elbow_angle': 1.0,    # 肘部角度
    'min_knee_angle': 1.2,     # 膝盖弯曲（反映蓄力深度，重要）
    'stance_width': 0.8,       # 站位宽度
    'contact_height': 1.3,     # 击球点高度（非常重要）
    'body_angle': 0.7,         # 身体角度
    'arm_extension': 1.1,      # 手臂伸展
    'pronation_angle': 1.2,    # 旋内角度（区分3.0和4.0的关键）
    'toss_height': 1.0,        # 抛球高度
    'weight_transfer': 1.1,    # 重心转移
    'shoulder_rotation': 1.0   # 肩部旋转
}

def extract_metrics(phase_analysis):
    """从五阶段分析中提取多维度指标"""
    metrics = {}
    
    # Loading 阶段 - 肘部角度（奖杯姿势）
    loading = phase_analysis.get('loading', {})
    if loading and 'max_elbow_angle' in loading:
        metrics['max_elbow_angle'] = loading['max_elbow_angle']
    
    # Ready 阶段 - 膝盖角度
    ready = phase_analysis.get('ready', {})
    if ready and 'min_knee_angle' in ready:
        metrics['min_knee_angle'] = ready['min_knee_angle']
    elif ready and 'stance_width' in ready:
        # 从站位宽度推断膝盖角度
        stance = ready['stance_width']
        if stance > 2.0:
            metrics['min_knee_angle'] = 90
        else:
            metrics['min_knee_angle'] = 120
    
    # Ready 阶段 - 站位宽度
    if ready and 'stance_width' in ready:
        metrics['stance_width'] = ready['stance_width']
    
    # Ready 阶段 - 身体角度
    if ready and 'body_angle' in ready:
        metrics['body_angle'] = ready['body_angle']
    
    # Contact 阶段 - 击球高度
    contact = phase_analysis.get('contact', {})
    if contact and 'contact_height' in contact:
        metrics['contact_height'] = contact['contact_height']
    
    return metrics

def query_gold_standard(db_path, level):
    """查询数据库中的黄金标准"""
    try:
        import sqlite3
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT standards_json FROM level_gold_standards WHERE level = ?",
            (level,)
        )
        row = cursor.fetchone()
        conn.close()
        if row:
            import json
            return json.loads(row[0])
    except Exception as e:
        print(f"[GoldStandard] 查询失败: {e}")
    return None

def compute_similarity(metrics, gold_standard):
    """计算与黄金标准的相似度"""
    if not gold_standard or 'key_features' not in gold_standard:
        return 0.5
    
    similarities = []
    gold_features = gold_standard.get('key_features', {})
    
    for feature, value in metrics.items():
        if feature in gold_features:
            gold_range = gold_features[feature]
            if isinstance(gold_range, (list, tuple)) and len(gold_range) == 2:
                min_val, max_val = gold_range
                mid = (min_val + max_val) / 2
                range_size = max_val - min_val
                
                if min_val <= value <= max_val:
                    diff = abs(value - mid)
                    similarity = max(0, 1 - diff / (range_size / 2))
                else:
                    diff = min(abs(value - min_val), abs(value - max_val))
                    similarity = max(0, 0.5 - diff / range_size)
                
                similarities.append(similarity)
    
    return sum(similarities) / len(similarities) if similarities else 0.5

def apply_level_caps(metrics, level_scores):
    """
    根据硬约束限制最高可评等级
    某些指标如果严重不达标，直接限制最高等级
    """
    caps = []
    
    # 膝盖角度 > 130° → 最高 2.0（没有蓄力）
    if metrics.get('min_knee_angle', 0) > 130:
        caps.append('2.0')
    # 膝盖角度 > 110° → 最高 3.0
    elif metrics.get('min_knee_angle', 0) > 110:
        caps.append('3.0')
    
    # 站位宽度 < 0.5 → 最高 2.0
    if metrics.get('stance_width', 1.0) < 0.5:
        caps.append('2.0')
    
    # 击球点高度过低 → 最高 3.0
    if metrics.get('contact_height', 1.0) < 0.3:
        caps.append('3.0')
    
    # 应用限制：如果有限制，高于限制的等级得分归零
    if caps:
        max_allowed = min(caps, key=lambda x: float(x.replace('+', '')))
        for level in list(level_scores.keys()):
            if float(level.replace('+', '')) > float(max_allowed.replace('+', '')):
                level_scores[level] = 0
    
    return level_scores

def evaluate_ntrp_level(phase_analysis, db_path=None):
    """
    多维度 NTRP 等级评估（带短板惩罚和权重）
    数据来源优先级：
    1. LEVEL_MODELS (基准模型)
    2. level_gold_standards (数据库黄金标准)
    3. ntrp_calibration_samples (校准样本)
    """
    if not phase_analysis:
        return '2.0', 0.0, {}
    
    # === 1. 从 MediaPipe 分析中提取多维度指标 ===
    metrics = extract_metrics(phase_analysis)
    
    if not metrics:
        return '2.0', 0.0, {}
    
    # === 2. 对每个等级计算匹配度 ===
    level_scores = {}
    feature_breakdown = {}  # 记录每个特征的得分详情
    
    for level, model in LEVEL_MODELS.items():
        feature_scores = []
        feature_weights = []
        feature_names = []
        
        for feature_name, (feat_min, feat_max) in model['key_features'].items():
            if feature_name not in metrics:
                continue
            
            value = metrics[feature_name]
            mid = (feat_min + feat_max) / 2
            range_size = max(feat_max - feat_min, 1)
            
            if feat_min <= value <= feat_max:
                # 在范围内：根据接近中心点的程度打分
                diff = abs(value - mid)
                score = max(0, 100 - (diff / (range_size / 2)) * 50)
            else:
                # 超出范围：惩罚更重（从30分开始扣）
                if value < feat_min:
                    distance = feat_min - value
                else:
                    distance = value - feat_max
                score = max(0, 30 - distance * 3)  # 更严厉的惩罚
            
            # 应用特征权重
            weight = FEATURE_WEIGHTS.get(feature_name, 1.0)
            feature_scores.append(score)
            feature_weights.append(weight)
            feature_names.append(feature_name)
        
        if not feature_scores:
            level_scores[level] = 0
            continue
        
        # ===== 关键修改：短板惩罚机制 =====
        min_score = min(feature_scores)  # 最低分（最差的维度）
        
        # 加权平均
        weighted_sum = sum(s * w for s, w in zip(feature_scores, feature_weights))
        total_weight = sum(feature_weights)
        weighted_avg = weighted_sum / total_weight
        
        # 最终得分 = 加权平均 * 0.5 + 最低分 * 0.5
        # 任何一个维度不达标，整体分数都会被大幅拉低
        combined = weighted_avg * 0.5 + min_score * 0.5
        
        # 如果有指标得分 < 20（严重不达标），额外惩罚
        severe_penalty = sum(1 for s in feature_scores if s < 20)
        if severe_penalty > 0:
            combined *= max(0.3, 1 - severe_penalty * 0.2)
        
        # 数据库黄金标准加成
        if db_path:
            gold = query_gold_standard(db_path, level)
            if gold:
                similarity = compute_similarity(metrics, gold)
                combined = combined * 0.7 + similarity * 100 * 0.3
        
        level_scores[level] = round(combined, 1)
        feature_breakdown[level] = dict(zip(feature_names, feature_scores))
    
    # === 3. 应用等级硬约束 ===
    level_scores = apply_level_caps(metrics, level_scores)
    
    # === 4. 选择最佳匹配等级 ===
    best_level = max(level_scores, key=lambda x: level_scores[x])
    best_score = level_scores[best_level]
    
    # ===== 关键修改：低分保护 =====
    # 如果最高分都低于40，说明检测数据质量差或发球水平确实很低
    # 不应该给出高等级
    if best_score < 40:
        for level, model in sorted(LEVEL_MODELS.items(), key=lambda x: float(x[0].replace('+', ''))):
            low, high = model['score_range']
            if low <= best_score <= high:
                best_level = level
                break
        else:
            best_level = '2.0'
    
    # 计算置信度（基于等级间差距和分数大小）
    sorted_scores = sorted(level_scores.values(), reverse=True)
    if len(sorted_scores) >= 2 and sorted_scores[0] > 0:
        gap = sorted_scores[0] - sorted_scores[1]  # 与第二名的差距
        score_magnitude = sorted_scores[0] / 100
        confidence = min(0.95, gap / 50 * 0.5 + score_magnitude * 0.5)
    else:
        confidence = 0.3
    
    return best_level, round(confidence, 2), {
        'level_scores': level_scores,
        'metrics': metrics,
        'feature_breakdown': feature_breakdown,
        'model_used': 'LEVEL_MODELS_v2_tuned',
        'evaluation_method': 'multi_dimensional_with_shortboard_penalty'
    }

def save_to_sample_library(video_url, analysis_result, ntrp_level, confidence):
    """
    将分析结果保存到样本库
    支持两种COS路径: videos/ 和 private-ai-learning/raw_videos/
    返回: (success, message)
    """
    try:
        import sqlite3
        from uuid import uuid4
        
        DB_PATH = '/data/db/xiaolongxia_learning.db'
        
        # 确保数据库和表存在
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # 创建样本表（如果不存在）
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS auto_analysis_samples (
                id TEXT PRIMARY KEY,
                video_url TEXT,
                cos_key TEXT,
                filename TEXT,
                source_path TEXT,
                ntrp_level TEXT,
                confidence REAL,
                analysis_result TEXT,
                total_phases INTEGER,
                has_knowledge_recall BOOLEAN,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                sample_type TEXT DEFAULT 'auto_analyzed'
            )
        ''')
        
        # 提取文件名和COS key
        filename = video_url.split('/')[-1].split('?')[0] if video_url else 'unknown.mp4'
        
        # 判断来源路径
        if 'private-ai-learning' in video_url:
            source_path = 'wechat_bot'
            # 从URL中提取完整的COS key
            cos_key = video_url.replace(f'{COS_BASE_URL}/', '').split('?')[0]
        elif 'videos/' in video_url:
            source_path = 'feishot_bot'
            cos_key = f"videos/{filename}"
        else:
            source_path = 'unknown'
            cos_key = f"videos/{filename}"
        
        # 检查是否已存在
        cursor.execute('SELECT id FROM auto_analysis_samples WHERE video_url = ?', (video_url,))
        if cursor.fetchone():
            conn.close()
            return False, 'Sample already exists'
        
        # 插入新样本
        sample_id = str(uuid4())
        summary = analysis_result.get('summary', {})
        
        cursor.execute('''
            INSERT INTO auto_analysis_samples 
            (id, video_url, cos_key, filename, source_path, ntrp_level, confidence, 
             analysis_result, total_phases, has_knowledge_recall, sample_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            sample_id,
            video_url,
            cos_key,
            filename,
            source_path,
            ntrp_level,
            confidence,
            json.dumps(analysis_result),
            summary.get('total_phases_detected', 0),
            summary.get('has_knowledge_recall', False),
            'auto_analyzed'
        ))
        
        conn.commit()
        conn.close()
        
        return True, f'Saved as {ntrp_level} level from {source_path} (confidence: {confidence:.2f})'
        
    except Exception as e:
        return False, f'Error: {str(e)}'


class Normalizer:
    """基于骨骼点的归一化"""
    
    def __init__(self, landmarks):
        left_shoulder = np.array([landmarks['left_shoulder']['x'], 
                                  landmarks['left_shoulder']['y']])
        right_shoulder = np.array([landmarks['right_shoulder']['x'], 
                                   landmarks['right_shoulder']['y']])
        self.shoulder_width = np.linalg.norm(left_shoulder - right_shoulder)
        
        head = np.array([landmarks['nose']['x'], landmarks['nose']['y']])
        left_ankle = np.array([landmarks['left_ankle']['x'], 
                               landmarks['left_ankle']['y']])
        right_ankle = np.array([landmarks['right_ankle']['x'], 
                                landmarks['right_ankle']['y']])
        ankle_center = (left_ankle + right_ankle) / 2
        self.height = np.linalg.norm(head - ankle_center)
    
    def normalize_distance(self, dist):
        return dist / self.shoulder_width if self.shoulder_width > 0 else 0


def extract_landmarks(pose_landmarks):
    """提取关键骨骼点"""
    if not pose_landmarks:
        return {}
    
    landmarks = pose_landmarks[0]
    
    return {
        'nose': {'x': landmarks[0].x, 'y': landmarks[0].y, 'z': landmarks[0].z},
        'left_shoulder': {'x': landmarks[11].x, 'y': landmarks[11].y, 'z': landmarks[11].z},
        'right_shoulder': {'x': landmarks[12].x, 'y': landmarks[12].y, 'z': landmarks[12].z},
        'left_elbow': {'x': landmarks[13].x, 'y': landmarks[13].y, 'z': landmarks[13].z},
        'right_elbow': {'x': landmarks[14].x, 'y': landmarks[14].y, 'z': landmarks[14].z},
        'left_wrist': {'x': landmarks[15].x, 'y': landmarks[15].y, 'z': landmarks[15].z},
        'right_wrist': {'x': landmarks[16].x, 'y': landmarks[16].y, 'z': landmarks[16].z},
        'left_hip': {'x': landmarks[23].x, 'y': landmarks[23].y, 'z': landmarks[23].z},
        'right_hip': {'x': landmarks[24].x, 'y': landmarks[24].y, 'z': landmarks[24].z},
        'left_knee': {'x': landmarks[25].x, 'y': landmarks[25].y, 'z': landmarks[25].z},
        'right_knee': {'x': landmarks[26].x, 'y': landmarks[26].y, 'z': landmarks[26].z},
        'left_ankle': {'x': landmarks[27].x, 'y': landmarks[27].y, 'z': landmarks[27].z},
        'right_ankle': {'x': landmarks[28].x, 'y': landmarks[28].y, 'z': landmarks[28].z},
    }


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def analyze_video(video_path):
    """分析视频并返回五阶段结果"""
    
    if not os.path.exists(MODEL_PATH):
        return {"error": f"模型文件不存在: {MODEL_PATH}"}
    
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"error": "无法打开视频文件"}
    
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    
    # 初始化MediaPipe
    try:
        base_options = BaseOptions(model_asset_path=MODEL_PATH)
        options = vision.PoseLandmarkerOptions(
            base_options=base_options,
            running_mode=vision.RunningMode.VIDEO,
            num_poses=1,
            min_pose_detection_confidence=0.5,
            min_pose_presence_confidence=0.5,
            min_tracking_confidence=0.5
        )
        landmarker = vision.PoseLandmarker.create_from_options(options)
    except Exception as e:
        return {"error": f"MediaPipe初始化失败: {str(e)}"}
    
    # 骨骼点检测
    pose_sequence = []
    frame_count = 0
    
    while cap.isOpened():
        ret, frame = cap.read()
        if not ret:
            break
        
        frame_count += 1
        if frame_count % 3 != 0:
            continue
        
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        
        timestamp_ms = int((frame_count / fps) * 1000) if fps > 0 else 0
        result = landmarker.detect_for_video(mp_image, timestamp_ms)
        
        landmarks = extract_landmarks(result.pose_landmarks)
        if landmarks:
            landmarks['frame'] = frame_count
            landmarks['timestamp'] = frame_count / fps if fps > 0 else 0
            pose_sequence.append(landmarks)
    
    cap.release()
    landmarker.close()
    
    if len(pose_sequence) < 10:
        return {"error": "检测到的姿态数据不足"}
    
    # 五阶段检测
    phases = detect_phases(pose_sequence)
    
    # 五阶段分析
    phase_analysis = analyze_phases(pose_sequence, phases)
    
    # 添加杨超教练知识召回
    print("[Analysis] 召回杨超教练知识点...")
    phase_analysis_with_knowledge = enrich_analysis_with_knowledge(phase_analysis)
    
    # 统计知识召回情况
    total_knowledge = sum(
        len(p.get('recalled_knowledge', []))
        for p in phase_analysis_with_knowledge.values()
        if p
    )
    
    return {
        "version": "2.0-knowledge",
        "analysis_time": datetime.now().isoformat(),
        "video_info": {
            "fps": float(fps),
            "total_frames": total_frames,
            "duration_seconds": float(duration),
            "analyzed_frames": len(pose_sequence)
        },
        "system_config": SYSTEM_CONFIG,
        "phases": phases,
        "phase_analysis": phase_analysis_with_knowledge,
        "knowledge_recall_summary": {
            "total_recalled": total_knowledge,
            "knowledge_base_version": "unified_v3",
            "coaches": ["杨超", "赵凌曦", "fuzzy_yellow"],
            "description": "三教练融合知识库"
        },
        "summary": {
            "total_phases_detected": len(phases),
            "average_confidence": np.mean([p['confidence'] for p in phases]) if phases else 0.0,
            "has_all_phases": len(phases) == 5,
            "has_knowledge_recall": total_knowledge > 0
        }
    }


def detect_phases(pose_sequence):
    """检测五阶段"""
    phases = []
    
    # Ready阶段
    phases.append({
        'phase': 'ready',
        'start_frame': 0,
        'end_frame': min(10, len(pose_sequence) - 1),
        'confidence': 0.85
    })
    
    # Toss阶段
    left_wrist_heights = [(i, p['left_wrist']['y']) for i, p in enumerate(pose_sequence) if 'left_wrist' in p]
    if left_wrist_heights:
        toss_peak = min(left_wrist_heights, key=lambda x: x[1])[0]
        phases.append({
            'phase': 'toss',
            'start_frame': max(0, toss_peak - 5),
            'end_frame': min(len(pose_sequence) - 1, toss_peak + 3),
            'confidence': 0.80
        })
    
    # Loading阶段
    elbow_angles = []
    for i, pose in enumerate(pose_sequence):
        if all(k in pose for k in ['right_shoulder', 'right_elbow', 'right_wrist']):
            angle = calculate_elbow_angle(pose)
            elbow_angles.append((i, angle))
    
    if elbow_angles:
        loading_peak = max(elbow_angles, key=lambda x: x[1])[0]
        phases.append({
            'phase': 'loading',
            'start_frame': max(0, loading_peak - 3),
            'end_frame': min(len(pose_sequence) - 1, loading_peak + 3),
            'confidence': 0.75
        })
    
    # Contact阶段
    right_wrist_heights = [(i, p['right_wrist']['y']) for i, p in enumerate(pose_sequence) if 'right_wrist' in p]
    if right_wrist_heights:
        contact_peak = min(right_wrist_heights, key=lambda x: x[1])[0]
        phases.append({
            'phase': 'contact',
            'start_frame': max(0, contact_peak - 2),
            'end_frame': min(len(pose_sequence) - 1, contact_peak + 2),
            'confidence': 0.80
        })
    
    # Follow阶段
    if phases:
        last_end = max([p['end_frame'] for p in phases])
        phases.append({
            'phase': 'follow',
            'start_frame': last_end,
            'end_frame': len(pose_sequence) - 1,
            'confidence': 0.85
        })
    
    return phases


def analyze_phases(pose_sequence, phases):
    """分析各阶段"""
    results = {}
    
    for phase_info in phases:
        phase_name = phase_info['phase']
        start = phase_info['start_frame']
        end = phase_info['end_frame']
        
        if start >= len(pose_sequence) or end >= len(pose_sequence):
            continue
        
        poses = pose_sequence[start:end+1]
        
        if phase_name == 'ready':
            results[phase_name] = analyze_ready(poses, phase_info)
        elif phase_name == 'toss':
            results[phase_name] = analyze_toss(poses, phase_info)
        elif phase_name == 'loading':
            results[phase_name] = analyze_loading(poses, phase_info)
        elif phase_name == 'contact':
            results[phase_name] = analyze_contact(poses, phase_info)
        elif phase_name == 'follow':
            results[phase_name] = analyze_follow(poses, phase_info)
    
    return results


def analyze_ready(poses, phase_info):
    """分析Ready阶段"""
    if not poses:
        return {}
    
    normalizer = Normalizer(poses[0])
    
    left_ankle = np.array([poses[0]['left_ankle']['x'], poses[0]['left_ankle']['y']])
    right_ankle = np.array([poses[0]['right_ankle']['x'], poses[0]['right_ankle']['y']])
    stance_width = normalizer.normalize_distance(np.linalg.norm(left_ankle - right_ankle))
    
    left_shoulder = np.array([poses[0]['left_shoulder']['x'], poses[0]['left_shoulder']['y']])
    right_shoulder = np.array([poses[0]['right_shoulder']['x'], poses[0]['right_shoulder']['y']])
    shoulder_line = right_shoulder - left_shoulder
    body_angle = abs(np.degrees(np.arctan2(shoulder_line[1], shoulder_line[0])))
    
    issues = {}
    if stance_width < 1.2:
        issues['stance_width_error'] = min(1.0, (1.2 - stance_width) * 2 + 0.5)
    elif stance_width > 2.8:
        issues['stance_width_error'] = min(1.0, (stance_width - 2.8) * 2 + 0.5)
    else:
        issues['stance_width_error'] = 0.0
    
    angle_deviation = abs(body_angle - 45)
    if angle_deviation > 10:
        issues['body_angle_error'] = min(1.0, angle_deviation / 30)
    else:
        issues['body_angle_error'] = 0.0
    
    return {
        'phase': 'ready',
        'duration_frames': len(poses),
        'stance_width': float(stance_width),
        'body_angle': float(body_angle),
        'issues': issues,
        'confidence': phase_info['confidence']
    }


def analyze_toss(poses, phase_info):
    """分析Toss阶段"""
    if not poses or len(poses) < 2:
        return {}
    
    wrist_heights = [p['left_wrist']['y'] for p in poses if 'left_wrist' in p]
    if not wrist_heights:
        return {}
    
    height_change = max(wrist_heights) - min(wrist_heights)
    duration = len(poses) / SYSTEM_CONFIG['fps']
    velocity = height_change / duration if duration > 0 else 0
    
    return {
        'phase': 'toss',
        'duration_frames': len(poses),
        'duration_seconds': float(duration),
        'height_change': float(height_change),
        'velocity': float(velocity),
        'issues': {},
        'confidence': phase_info['confidence']
    }


def analyze_loading(poses, phase_info):
    """分析Loading阶段"""
    if not poses:
        return {}
    
    elbow_angles = []
    for pose in poses:
        if all(k in pose for k in ['right_shoulder', 'right_elbow', 'right_wrist']):
            angle = calculate_elbow_angle(pose)
            elbow_angles.append(angle)
    
    max_angle = max(elbow_angles) if elbow_angles else 0
    
    issues = {}
    if max_angle < 90:
        issues['elbow_angle_error'] = min(1.0, (90 - max_angle) / 30)
    else:
        issues['elbow_angle_error'] = 0.0
    
    return {
        'phase': 'loading',
        'duration_frames': len(poses),
        'max_elbow_angle': float(max_angle),
        'issues': issues,
        'confidence': phase_info['confidence']
    }


def analyze_contact(poses, phase_info):
    """分析Contact阶段"""
    if not poses:
        return {}
    
    wrist_heights = [(i, p['right_wrist']['y']) for i, p in enumerate(poses) if 'right_wrist' in p]
    if not wrist_heights:
        return {}
    
    contact_idx = min(wrist_heights, key=lambda x: x[1])[0]
    contact_pose = poses[contact_idx]
    
    return {
        'phase': 'contact',
        'duration_frames': len(poses),
        'contact_height': float(contact_pose['right_wrist']['y']),
        'issues': {},
        'confidence': phase_info['confidence']
    }


def analyze_follow(poses, phase_info):
    """分析Follow阶段"""
    if not poses:
        return {}
    
    return {
        'phase': 'follow',
        'duration_frames': len(poses),
        'issues': {},
        'confidence': phase_info['confidence']
    }


def calculate_elbow_angle(pose):
    """计算肘部角度"""
    shoulder = np.array([pose['right_shoulder']['x'], pose['right_shoulder']['y']])
    elbow = np.array([pose['right_elbow']['x'], pose['right_elbow']['y']])
    wrist = np.array([pose['right_wrist']['x'], pose['right_wrist']['y']])
    
    vec1 = shoulder - elbow
    vec2 = wrist - elbow
    
    cos_angle = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2) + 1e-6)
    cos_angle = np.clip(cos_angle, -1.0, 1.0)
    return np.degrees(np.arccos(cos_angle))


def load_knowledge_base():
    """加载统一知识库（3位教练融合版）"""
    global _knowledge_base_cache, _knowledge_base_loaded
    
    if _knowledge_base_loaded:
        return _knowledge_base_cache
    
    try:
        # 尝试从本地加载（统一知识库v3）
        local_path = '/tmp/unified_knowledge_v3.json'
        if os.path.exists(local_path):
            with open(local_path, 'r', encoding='utf-8') as f:
                _knowledge_base_cache = json.load(f)
                _knowledge_base_loaded = True
                coaches = [c.get('coach_name', 'Unknown') for c in _knowledge_base_cache.get('coaches', [])]
                total = _knowledge_base_cache.get('total_items', 0)
                print(f"[Knowledge] 从本地加载统一知识库: {total} 条知识点")
                print(f"[Knowledge] 包含教练: {', '.join(coaches)}")
                return _knowledge_base_cache
        
        # 从 COS 下载
        print(f"[Knowledge] 从 COS 下载统一知识库...")
        req = urllib.request.Request(KNOWLEDGE_BASE_URL)
        with urllib.request.urlopen(req, timeout=30) as response:
            _knowledge_base_cache = json.loads(response.read().decode('utf-8'))
            _knowledge_base_loaded = True
            # 缓存到本地
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(_knowledge_base_cache, f, ensure_ascii=False)
            coaches = [c.get('coach_name', 'Unknown') for c in _knowledge_base_cache.get('coaches', [])]
            total = _knowledge_base_cache.get('total_items', 0)
            print(f"[Knowledge] 统一知识库加载成功: {total} 条知识点")
            print(f"[Knowledge] 包含教练: {', '.join(coaches)}")
            return _knowledge_base_cache
    except Exception as e:
        print(f"[Knowledge] 知识库加载失败: {e}")
        _knowledge_base_cache = {'knowledge_items': []}
        _knowledge_base_loaded = True
        return _knowledge_base_cache


def recall_knowledge(phase, issue_tags, limit=3):
    """
    根据 phase 和 issue_tags 召回知识点（支持3位教练）
    
    Args:
        phase: 阶段名称 (ready/toss/loading/contact/follow)
        issue_tags: 问题标签列表
        limit: 返回结果数量限制
    
    Returns:
        匹配的知识点列表（包含coach_id和coach_name）
    """
    knowledge_base = load_knowledge_base()
    knowledge_items = knowledge_base.get('knowledge_items', [])
    
    if not knowledge_items or not issue_tags:
        return []
    
    matched = []
    
    for item in knowledge_items:
        # 检查 phase 匹配
        item_phases = item.get('phase', [])
        if isinstance(item_phases, str):
            item_phases = [item_phases]
        
        phase_match = phase in item_phases
        
        # 检查 issue_tags 匹配
        item_tags = item.get('issue_tags', [])
        matched_tags = [tag for tag in issue_tags if tag in item_tags]
        tag_match = len(matched_tags) > 0
        
        # 计算匹配分数
        if phase_match or tag_match:
            score = 0
            match_reason = []
            
            if phase_match:
                score += 0.5
                match_reason.append(f"phase:{phase}")
            
            if tag_match:
                tag_score = 0.5 * (len(matched_tags) / len(issue_tags))
                score += tag_score
                match_reason.append(f"tags:{','.join(matched_tags)}")
            
            matched.append({
                'knowledge_id': item.get('knowledge_id', ''),
                'coach_id': item.get('coach_id', ''),
                'coach_name': item.get('coach_name', ''),
                'title': item.get('title', ''),
                'content': item.get('knowledge_summary', item.get('content', '')),
                'knowledge_type': item.get('knowledge_type', ''),
                'quality_grade': item.get('quality_grade', ''),
                'phase': item_phases,
                'issue_tags': item_tags,
                'source_video': item.get('source_video_name', ''),
                'key_elements': item.get('key_elements', []),
                'common_errors': item.get('common_errors', []),
                'correction_method': item.get('correction_method', []),
                'match_score': round(score, 3),
                'match_reason': match_reason
            })
    
    # 按匹配分数排序
    matched.sort(key=lambda x: x['match_score'], reverse=True)
    
    return matched[:limit]


def enrich_analysis_with_knowledge(phase_analysis):
    """
    为分析结果添加杨超教练知识召回
    
    Args:
        phase_analysis: 阶段分析结果字典
    
    Returns:
        添加了知识召回的分析结果
    """
    enriched = {}
    
    for phase_name, analysis in phase_analysis.items():
        if not analysis:
            enriched[phase_name] = analysis
            continue
        
        # 获取该阶段的 issues
        issues = analysis.get('issues', {})
        issue_tags = [tag for tag, score in issues.items() if score > 0.3]  # 只召回置信度>0.3的问题
        
        # 召回相关知识
        recalled_knowledge = recall_knowledge(phase_name, issue_tags, limit=3)
        
        # 添加知识召回到分析结果
        analysis_with_knowledge = analysis.copy()
        analysis_with_knowledge['recalled_knowledge'] = recalled_knowledge
        analysis_with_knowledge['knowledge_summary'] = {
            'total_recalled': len(recalled_knowledge),
            'issue_tags_matched': issue_tags,
            'has_knowledge': len(recalled_knowledge) > 0
        }
        
        enriched[phase_name] = analysis_with_knowledge
    
    return enriched


# API路由
@app.route('/health', methods=['GET'])
def health_check():
    """健康检查"""
    knowledge_base = load_knowledge_base()
    knowledge_items = knowledge_base.get('knowledge_items', [])
    coaches = knowledge_base.get('coaches', [])
    
    return jsonify({
        'status': 'ok',
        'mediapipe_available': MEDIAPIPE_AVAILABLE,
        'model_exists': os.path.exists(MODEL_PATH),
        'knowledge_base_loaded': len(knowledge_items) > 0,
        'knowledge_items_count': len(knowledge_items),
        'coaches': [c.get('coach_name', 'Unknown') for c in coaches],
        'knowledge_base_version': knowledge_base.get('version', 'unknown'),
        'version': '2.1-unified-knowledge',
        'timestamp': datetime.now().isoformat()
    })


def download_video_from_url(url, output_path, timeout=120):
    """从URL下载视频文件"""
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36')
        
        with urllib.request.urlopen(req, timeout=timeout) as response:
            with open(output_path, 'wb') as f:
                f.write(response.read())
        return True
    except Exception as e:
        print(f"[Download] 下载失败: {e}")
        return False


@app.route('/analyze', methods=['POST'])
def analyze():
    """分析视频文件 - 支持文件上传或URL"""
    filepath = None
    video_url = None  # 初始化 video_url
    
    # 检查是否是JSON请求（包含videoUrl）
    if request.is_json:
        data = request.get_json()
        video_url = data.get('videoUrl') or data.get('video_url')
        
        if video_url:
            # 从URL下载视频
            filename = secure_filename(video_url.split('/')[-1].split('?')[0]) or 'video.mp4'
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            
            print(f"[Analyze] 从URL下载视频: {video_url}")
            if not download_video_from_url(video_url, filepath):
                return jsonify({'error': 'Failed to download video from URL'}), 400
            print(f"[Analyze] 视频下载完成: {filepath}")
    
    # 检查是否是文件上传
    elif 'video' in request.files:
        file = request.files['video']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Allowed: mp4, mov, avi, mkv'}), 400
        
        # 保存上传的文件
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
    
    else:
        return jsonify({'error': 'No video file or URL provided. Use "video" file field or JSON {"videoUrl": "..."}'}), 400
    
    if not filepath or not os.path.exists(filepath):
        return jsonify({'error': 'Video file not found'}), 400
    
    try:
        # 分析视频
        result = analyze_video(filepath)
        
        # 清理临时文件
        if os.path.exists(filepath):
            os.remove(filepath)
        
        if 'error' in result:
            return jsonify(result), 500
        
        # 自动评分
        print("[Analyze] 自动评估 NTRP 等级...")
        phase_analysis = result.get('phase_analysis', {})
        ntrp_level, confidence, eval_details = evaluate_ntrp_level(phase_analysis, DB_PATH)
        
        # 添加到结果
        result['ntrp_evaluation'] = {
            'level': ntrp_level,
            'confidence': round(confidence, 3),
            'details': eval_details
        }
        
        # 自动入库到样本库
        if video_url:
            print(f"[Analyze] 保存到样本库: {ntrp_level}级 (置信度: {confidence:.2f})")
            success, message = save_to_sample_library(video_url, result, ntrp_level, confidence)
            result['sample_library'] = {
                'saved': success,
                'message': message
            }
        
        return jsonify(result)
    
    except Exception as e:
        # 清理临时文件
        if filepath and os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'error': str(e)}), 500


@app.route('/', methods=['GET'])
def index():
    """首页"""
    return jsonify({
        'service': 'Five Phase Tennis Serve Analysis API with Unified Knowledge Base',
        'version': '2.3-three-coaches',
        'coaches': ['杨超', '赵凌曦', 'fuzzy_yellow'],
        'features': [
            '五阶段发球分析 (Ready/Toss/Loading/Contact/Follow)',
            'MediaPipe 33关键点检测',
            '三教练融合知识库智能召回 (杨超+赵凌曦+fuzzy_yellow)',
            '支持文件上传或COS URL分析',
            '自动NTRP等级评估',
            '自动入库到样本库',
            '统一COS路径支持 (videos/ & private-ai-learning/)'
        ],
        'endpoints': {
            '/health': 'Health check with knowledge base status',
            '/analyze': 'POST - Upload video file OR JSON with videoUrl (auto saves to library)'
        },
        'usage': {
            'file_upload': 'curl -X POST http://localhost:5000/analyze -F "video=@video.mp4"',
            'url_analysis': 'curl -X POST http://localhost:5000/analyze -H "Content-Type: application/json" -d \'{"videoUrl": "https://..."}\''
        },
        'cos_paths': {
            'wechat_bot': 'private-ai-learning/raw_videos/{date}/',
            'feishu_bot': 'videos/'
        }
    })


if __name__ == '__main__':
    print("="*60)
    print("五阶段网球发球分析服务 v2.3")
    print("集成三教练融合知识库（杨超+赵凌曦+fuzzy_yellow）")
    print("="*60)
    print(f"MediaPipe可用: {MEDIAPIPE_AVAILABLE}")
    print(f"模型文件: {MODEL_PATH}")
    print(f"模型存在: {os.path.exists(MODEL_PATH)}")
    print(f"知识库URL: {KNOWLEDGE_BASE_URL}")
    print("="*60)
    
    # 预加载知识库
    print("[Startup] 预加载统一知识库...")
    kb = load_knowledge_base()
    if kb.get('knowledge_items'):
        coaches = [c.get('coach_name', 'Unknown') for c in kb.get('coaches', [])]
        print(f"[Startup] 知识库加载成功: {kb.get('total_items', 0)} 条知识点")
        print(f"[Startup] 包含教练: {', '.join(coaches)}")
    else:
        print("[Startup] 警告: 知识库为空或加载失败")
    print("="*60)
    
    # 运行Flask服务
    app.run(host='0.0.0.0', port=5000, debug=False)
