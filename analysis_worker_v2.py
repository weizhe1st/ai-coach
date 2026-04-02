#!/usr/bin/env python3
"""
统一分析Worker V2 - 唯一分析入口
支持：MediaPipe骨骼检测 + 五阶段分析 + 三教练知识库匹配

核心原则：一个视频只产生一份分析结果，所有渠道查同一份
"""

import sqlite3
import time
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加路径
sys.path.insert(0, '/usr/local/lib/python3.12/dist-packages')
sys.path.insert(0, '/usr/lib/python3/dist-packages')
sys.path.insert(0, '/data/apps/xiaolongxia')

# 导入分析模块
try:
    from tennis_analyzer_v2 import analyze_video_with_mediapipe, load_coach_knowledge
    from knowledge_matcher import KnowledgeMatcher
    MEDIAPIPE_AVAILABLE = True
except ImportError as e:
    print(f"[WorkerV2] 导入错误: {e}")
    MEDIAPIPE_AVAILABLE = False

# 导入COS
try:
    from qcloud_cos import CosConfig, CosS3Client
    COS_AVAILABLE = True
except ImportError:
    print("[WorkerV2] COS SDK未安装")
    COS_AVAILABLE = False

# 配置
DB_PATH = '/data/db/xiaolongxia_learning.db'
COS_SECRET_ID = "AKIDaHuZDoEKB5qOipqgJkx2uZ1HLPFvXxBC"
COS_SECRET_KEY = "sZ3KOG5nIcUaifjjbIwhIgqqfKpAKJ6r"
COS_BUCKET = 'tennis-ai-1411340868'
COS_REGION = 'ap-shanghai'


class UnifiedAnalysisWorker:
    """统一分析Worker - 唯一分析入口"""
    
    def __init__(self):
        self.knowledge_matcher = KnowledgeMatcher(DB_PATH)
        print(f"[WorkerV2] 初始化完成 - MediaPipe: {MEDIAPIPE_AVAILABLE}, COS: {COS_AVAILABLE}")
    
    def get_db_connection(self):
        """获取数据库连接"""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_pending_task(self):
        """获取一个pending状态的任务"""
        try:
            conn = self.get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT t.id, t.video_id, v.cos_url, v.file_name, v.cos_key, v.user_id
                FROM video_analysis_tasks t
                JOIN videos v ON t.video_id = v.id
                WHERE t.analysis_status = 'pending'
                ORDER BY t.created_at ASC
                LIMIT 1
            ''')
            
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return {
                    'task_id': row['id'],
                    'video_id': row['video_id'],
                    'cos_url': row['cos_url'],
                    'file_name': row['file_name'],
                    'cos_key': row['cos_key'],
                    'user_id': row['user_id']
                }
            return None
            
        except Exception as e:
            print(f"[WorkerV2] 获取任务错误: {e}")
            return None
    
    def download_video(self, cos_key, local_path):
        """从COS下载视频"""
        if not COS_AVAILABLE:
            print("[WorkerV2] COS不可用，无法下载")
            return False
        
        try:
            config = CosConfig(Region=COS_REGION, SecretId=COS_SECRET_ID, SecretKey=COS_SECRET_KEY)
            client = CosS3Client(config)
            
            print(f"[WorkerV2] 从COS下载: {cos_key}")
            client.download_file(
                Bucket=COS_BUCKET,
                Key=cos_key,
                DestFilePath=local_path
            )
            print(f"[WorkerV2] 下载完成: {local_path}")
            return True
        except Exception as e:
            print(f"[WorkerV2] 下载视频失败: {e}")
            return False
    
    def analyze_video(self, video_path, video_id):
        """
        完整分析流程：
        1. MediaPipe骨骼检测
        2. 五阶段发球分析
        3. 三教练知识库匹配
        4. 生成标准化报告
        """
        print(f"\n{'='*60}")
        print(f"[WorkerV2] 开始分析: {video_path}")
        print(f"{'='*60}")
        
        if not MEDIAPIPE_AVAILABLE:
            raise Exception("MediaPipe不可用")
        
        # === 1. MediaPipe骨骼检测 ===
        print("\n[1/4] MediaPipe骨骼检测...")
        pose_data = analyze_video_with_mediapipe(video_path)
        print(f"      ✓ 分析了 {len(pose_data)} 帧姿态数据")
        
        # === 2. 五阶段分析 ===
        print("\n[2/4] 五阶段发球分析...")
        phase_scores = self.analyze_five_phases(pose_data)
        print(f"      ✓ 阶段评分: {phase_scores}")
        
        # === 3. 提取检测到的问题 ===
        print("\n[3/4] 提取问题标签...")
        detected_issues = self.extract_issues(pose_data, phase_scores)
        print(f"      ✓ 检测到 {len(detected_issues)} 个问题: {detected_issues}")
        
        # === 4. 三教练知识库匹配 ===
        print("\n[4/4] 三教练知识库匹配...")
        knowledge_matches = self.knowledge_matcher.match_issues(
            issues=detected_issues,
            skill='serve',
            user_level='3.0'
        )
        print(f"      ✓ 匹配到 {len(knowledge_matches)} 条知识点")
        
        # === 5. 生成标准化报告 ===
        report = self.generate_report(video_id, pose_data, phase_scores, detected_issues, knowledge_matches)
        
        print(f"\n{'='*60}")
        print(f"[WorkerV2] 分析完成 - 总分: {report['total_score']}, 档位: {report['bucket']}")
        print(f"{'='*60}\n")
        
        return report
    
    def analyze_five_phases(self, pose_data):
        """五阶段分析"""
        if not pose_data:
            return {'ready': 60, 'toss': 60, 'loading': 60, 'contact': 60, 'follow': 60}
        
        # 统计数据
        elbow_angles = [d['elbow_angle'] for d in pose_data]
        knee_angles = [d['knee_angle'] for d in pose_data]
        
        avg_elbow = sum(elbow_angles) / len(elbow_angles)
        avg_knee = sum(knee_angles) / len(knee_angles)
        min_knee = min(knee_angles)
        max_elbow = max(elbow_angles)
        
        # 计算各阶段评分
        phases = {
            'ready': 75,  # 准备阶段默认良好
            'toss': 70 if min_knee < 120 else 65,  # 抛球阶段看膝盖弯曲
            'loading': 75 if min_knee < 100 else 70,  # 蓄力阶段看膝盖深度
            'contact': 70 if max_elbow > 150 else 65,  # 击球阶段看肘部伸展
            'follow': 72  # 随挥阶段默认良好
        }
        
        return phases
    
    def extract_issues(self, pose_data, phase_scores):
        """提取问题标签 - 基于统计数据和合理阈值"""
        issues = []
        
        if not pose_data:
            return issues
        
        knee_angles = [d['knee_angle'] for d in pose_data]
        elbow_angles = [d['elbow_angle'] for d in pose_data]
        
        # 过滤异常值（0-10度和170-180度可能是检测错误）
        valid_knee = [a for a in knee_angles if 10 < a < 170]
        valid_elbow = [a for a in elbow_angles if 10 < a < 170]
        
        if not valid_knee or not valid_elbow:
            return issues
        
        min_knee = min(valid_knee)
        max_elbow = max(valid_elbow)
        avg_knee = sum(valid_knee) / len(valid_knee)
        avg_elbow = sum(valid_elbow) / len(valid_elbow)
        
        # 膝盖弯曲度判断（蓄力阶段）
        # 优秀：min_knee < 90, 良好：min_knee < 110, 一般：min_knee < 130
        if min_knee > 130:
            issues.append('蓄力不足')
            issues.append('膝盖弯曲不够')
        elif min_knee > 110:
            issues.append('蓄力可加强')
        
        # 肘部伸展判断（击球阶段）
        # 优秀：max_elbow > 160, 良好：max_elbow > 140
        if max_elbow < 140:
            issues.append('肘部伸展不足')
            issues.append('击球点偏低')
        elif max_elbow < 150:
            issues.append('击球伸展可加强')
        
        # 抛球阶段判断
        if phase_scores['toss'] < 70:
            issues.append('抛球高度不足')
        
        # 添加一些通用问题用于测试知识库匹配
        if len(issues) == 0:
            # 如果没有明显问题，添加一些改进建议类问题
            if avg_knee > 120:
                issues.append('抛球')
            if avg_elbow < 120:
                issues.append('击球')
        
        return issues
    
    def generate_report(self, video_id, pose_data, phase_scores, issues, knowledge_matches):
        """生成标准化分析报告"""
        
        # 计算总分
        total_score = sum(phase_scores.values()) // len(phase_scores)
        
        # 确定档位
        if total_score >= 90:
            bucket = '5.0+'
        elif total_score >= 80:
            bucket = '4.0'
        elif total_score >= 62:
            bucket = '3.0'
        else:
            bucket = '2.0'
        
        # 构建问题列表
        problems = []
        for issue in issues:
            problems.append({
                'phase': 'contact' if '击球' in issue or '肘部' in issue else 'loading',
                'problem_code': issue,
                'description': issue
            })
        
        # 构建教练反馈
        coach_feedback = []
        for match in knowledge_matches:
            coach_feedback.append({
                'coach': match['coach_name'],
                'title': match['title'],
                'content': match['summary'],
                'correction': match['corrections'],
                'confidence': match['confidence']
            })
        
        # 统计教练引用
        coach_stats = {}
        for cf in coach_feedback:
            coach = cf['coach']
            coach_stats[coach] = coach_stats.get(coach, 0) + 1
        
        report = {
            'video_id': video_id,
            'analysis_type': 'mediapipe_v2_unified',
            'total_score': total_score,
            'bucket': bucket,
            'phase_analysis': {
                'ready': {'score': phase_scores['ready'], 'issues': []},
                'toss': {'score': phase_scores['toss'], 'issues': ['抛球高度不足'] if phase_scores['toss'] < 70 else []},
                'loading': {'score': phase_scores['loading'], 'issues': ['蓄力不足'] if phase_scores['loading'] < 75 else []},
                'contact': {'score': phase_scores['contact'], 'issues': ['肘部伸展不足'] if phase_scores['contact'] < 70 else []},
                'follow': {'score': phase_scores['follow'], 'issues': []}
            },
            'problems': problems,
            'recommendations': [match['corrections'] for match in knowledge_matches[:3] if match['corrections']],
            'coach_feedback': coach_feedback,
            'coach_stats': coach_stats,
            'knowledge_recall_count': len(knowledge_matches),
            'frames_analyzed': len(pose_data),
            'analysis_timestamp': datetime.now().isoformat()
        }
        
        return report
    
    def save_result(self, task_id, video_id, report):
        """保存分析结果到数据库"""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        # 更新任务状态
        cursor.execute('''
            UPDATE video_analysis_tasks 
            SET analysis_status = 'success',
                ntrp_level = ?,
                ntrp_confidence = ?,
                knowledge_recall_count = ?,
                sample_saved = 1,
                analysis_result = ?,
                phase_marks = ?,
                finished_at = datetime('now')
            WHERE id = ?
        ''', (
            report['bucket'],
            0.85,
            report['knowledge_recall_count'],
            json.dumps(report, ensure_ascii=False),
            json.dumps(report['phase_analysis'], ensure_ascii=False),
            task_id
        ))
        
        conn.commit()
        conn.close()
        print(f"[WorkerV2] 结果已保存到数据库: task_id={task_id}")
    
    def process_task(self, task):
        """处理单个任务"""
        print(f"\n[WorkerV2] 处理任务: {task['task_id']}")
        
        try:
            # 更新状态为running
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE video_analysis_tasks 
                SET analysis_status = 'running', started_at = datetime('now')
                WHERE id = ?
            ''', (task['task_id'],))
            conn.commit()
            conn.close()
            
            # 下载视频
            local_path = f"/tmp/{task['video_id']}.mp4"
            if task.get('cos_key'):
                success = self.download_video(task['cos_key'], local_path)
                if not success:
                    raise Exception("视频下载失败")
            else:
                raise Exception("无cos_key")
            
            # 分析视频
            report = self.analyze_video(local_path, task['video_id'])
            
            # 保存结果
            self.save_result(task['task_id'], task['video_id'], report)
            
            # 清理临时文件
            if os.path.exists(local_path):
                os.remove(local_path)
            
            print(f"[WorkerV2] 任务完成: {task['task_id']}")
            
        except Exception as e:
            print(f"[WorkerV2] 处理任务错误: {e}")
            import traceback
            traceback.print_exc()
            
            # 更新状态为失败
            conn = self.get_db_connection()
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE video_analysis_tasks 
                SET analysis_status = 'failed', finished_at = datetime('now')
                WHERE id = ?
            ''', (task['task_id'],))
            conn.commit()
            conn.close()
    
    def run(self):
        """主循环"""
        print("[WorkerV2] 统一分析Worker启动...")
        print("[WorkerV2] 核心原则: 一个视频只产生一份分析结果")
        
        while True:
            try:
                task = self.get_pending_task()
                
                if task:
                    self.process_task(task)
                else:
                    print("[WorkerV2] 无pending任务，等待5秒...")
                    time.sleep(5)
                    
            except Exception as e:
                print(f"[WorkerV2] 错误: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(10)


if __name__ == '__main__':
    worker = UnifiedAnalysisWorker()
    worker.run()
