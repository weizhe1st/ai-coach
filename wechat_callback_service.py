#!/usr/bin/env python3
"""
微信机器人回调服务
接收微信视频后，直传COS，创建分析任务
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
from uuid import uuid4
from flask import Flask, request, jsonify

# COS配置
COS_SECRET_ID = "AKIDaHuZDoEKB5qOipqgJkx2uZ1HLPFvXxBC"
COS_SECRET_KEY = "sZ3KOG5nIcUaifjjbIwhIgqqfKpAKJ6r"
COS_BUCKET = "tennis-ai-1411340868"
COS_REGION = "ap-shanghai"
COS_PREFIX = "private-ai-learning/raw_videos"

DB_PATH = '/data/db/xiaolongxia_learning.db'

app = Flask(__name__)


def get_db_connection():
    """获取数据库连接"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def upload_to_cos(local_path, file_name, user_id):
    """上传文件到腾讯云COS"""
    try:
        from qcloud_cos import CosConfig, CosS3Client
        
        config = CosConfig(Region=COS_REGION, SecretId=COS_SECRET_ID, SecretKey=COS_SECRET_KEY)
        cos_client = CosS3Client(config)
        
        date = datetime.now().strftime("%Y-%m-%d")
        cos_key = f"{COS_PREFIX}/{date}/{int(datetime.now().timestamp())}_{file_name}"
        
        print(f"[Upload] 上传到COS: {cos_key}")
        
        with open(local_path, 'rb') as fp:
            response = cos_client.put_object(
                Bucket=COS_BUCKET,
                Body=fp,
                Key=cos_key,
                ContentType='video/mp4'
            )
        
        cos_url = f"https://{COS_BUCKET}.cos.{COS_REGION}.myqcloud.com/{cos_key}"
        print(f"[Upload] ✅ 上传成功: {cos_url}")
        
        return True, cos_key, cos_url
        
    except Exception as e:
        print(f"[Upload] ❌ 上传失败: {e}")
        return False, None, str(e)


def create_video_record(user_id, source_channel, cos_key, cos_url, file_name, file_size_mb):
    """创建视频记录"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    video_id = str(uuid4())
    
    cursor.execute('''
        INSERT INTO videos (id, user_id, source_channel, cos_bucket, cos_key, cos_url, file_name, file_size_mb)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (video_id, user_id, source_channel, COS_BUCKET, cos_key, cos_url, file_name, file_size_mb))
    
    conn.commit()
    conn.close()
    
    return video_id


def create_analysis_task(video_id):
    """创建分析任务"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    task_id = str(uuid4())
    
    cursor.execute('''
        INSERT INTO video_analysis_tasks (id, video_id, analysis_status, analyzer_version, rule_version, level_model_version, report_template_version)
        VALUES (?, ?, 'pending', '2.2', 'v2', 'v1', 'v1')
    ''', (task_id, video_id))
    
    conn.commit()
    conn.close()
    
    return task_id


def create_task_from_cos(cos_url, cos_key, file_name, file_size_mb, user_id):
    """从COS URL创建分析任务"""
    try:
        # 1. 创建视频记录
        video_id = create_video_record(user_id, 'wechat', cos_key, cos_url, file_name, file_size_mb)
        print(f"[WeChat] 视频记录创建: {video_id}")
        
        # 2. 创建分析任务
        task_id = create_analysis_task(video_id)
        print(f"[WeChat] 分析任务创建: {task_id}")
        
        return {
            'success': True,
            'video_id': video_id,
            'task_id': task_id,
            'cos_url': cos_url,
            'status': 'pending'
        }
        
    except Exception as e:
        print(f"[WeChat] ❌ 创建任务失败: {e}")
        return {'success': False, 'error': str(e)}


@app.route('/webhook/wechat/video', methods=['POST'])
def handle_wechat_video():
    """处理微信视频上传 - 支持文件上传或COS URL"""
    try:
        user_id = request.form.get('user_id', 'unknown')
        
        # 检查是否是COS URL模式
        cos_url = request.form.get('cos_url')
        cos_key = request.form.get('cos_key')
        file_name = request.form.get('file_name', 'video.mp4')
        file_size_mb = request.form.get('file_size_mb', 0)
        
        if cos_url and cos_key:
            # COS URL模式（微信机器人已上传）
            print(f"[WeChat] 收到COS URL: {cos_key} from {user_id}")
            
            result = create_task_from_cos(cos_url, cos_key, file_name, float(file_size_mb), user_id)
            
            if result['success']:
                return jsonify({
                    'success': True,
                    'message': '已收到，正在分析',
                    **result
                })
            else:
                return jsonify({'error': 'Failed to create task', 'details': result.get('error')}), 500
        
        # 文件上传模式
        if 'video' not in request.files:
            return jsonify({'error': 'No video file or COS URL provided'}), 400
        
        file = request.files['video']
        if file.filename == '':
            return jsonify({'error': 'Empty filename'}), 400
        
        # 保存到临时文件
        temp_path = f"/tmp/wechat_video_{int(datetime.now().timestamp())}.mp4"
        file.save(temp_path)
        
        # 获取文件大小
        file_size_mb = os.path.getsize(temp_path) / (1024 * 1024)
        
        print(f"[WeChat] 收到视频: {file.filename} ({file_size_mb:.2f} MB) from {user_id}")
        
        # 1. 上传到COS
        success, cos_key, cos_url = upload_to_cos(temp_path, file.filename, user_id)
        
        if not success:
            os.remove(temp_path)
            return jsonify({'error': 'COS upload failed', 'details': cos_url}), 500
        
        # 2. 创建视频记录和任务
        result = create_task_from_cos(cos_url, cos_key, file.filename, file_size_mb, user_id)
        
        # 3. 清理临时文件
        os.remove(temp_path)
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': '已收到，正在分析',
                **result
            })
        else:
            return jsonify({'error': 'Failed to create task', 'details': result.get('error')}), 500
        
    except Exception as e:
        print(f"[WeChat] 处理失败: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/task/status/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """查询任务状态"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT t.*, v.cos_url
            FROM video_analysis_tasks t
            JOIN videos v ON t.video_id = v.id
            WHERE t.id = ?
        ''', (task_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({'error': 'Task not found'}), 404
        
        task = dict(row)
        
        # 根据状态返回不同信息
        response = {
            'task_id': task_id,
            'status': task['analysis_status'],
            'created_at': task['created_at'],
            'started_at': task['started_at'],
            'finished_at': task['finished_at']
        }
        
        if task['analysis_status'] == 'success':
            response['result'] = {
                'ntrp_level': task['ntrp_level'],
                'ntrp_confidence': task['ntrp_confidence'],
                'knowledge_recall_count': task['knowledge_recall_count'],
                'sample_saved': task['sample_saved']
            }
        elif task['analysis_status'] in ('failed', 'low_quality'):
            response['failure_reason'] = task['failure_reason']
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/task/report/<task_id>', methods=['GET'])
def get_task_report(task_id):
    """获取完整分析报告"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT t.*, v.file_name, v.cos_url, v.user_id
            FROM video_analysis_tasks t
            JOIN videos v ON t.video_id = v.id
            WHERE t.id = ?
        ''', (task_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if not row:
            return jsonify({'error': 'Task not found'}), 404
        
        task = dict(row)
        
        # 构建完整报告
        report = {
            'task_id': task_id,
            'status': task['analysis_status'],
            'file_name': task['file_name'],
            'created_at': task['created_at'],
            'started_at': task['started_at'],
            'finished_at': task['finished_at']
        }
        
        if task['analysis_status'] == 'success':
            report['ntrp_evaluation'] = {
                'level': task['ntrp_level'],
                'confidence': task['ntrp_confidence']
            }
            
            # 解析详细结果
            if task['analysis_result']:
                try:
                    result = json.loads(task['analysis_result'])
                    report['phase_marks'] = result.get('phase_marks', {})
                    report['features'] = result.get('features', {})
                except:
                    pass
            
            # 解析诊断
            if task['diagnosis']:
                try:
                    report['diagnosis'] = json.loads(task['diagnosis'])
                except:
                    pass
            
            # 解析输入质量
            if task['input_quality_issues']:
                try:
                    report['input_quality'] = {
                        'score': task['input_quality_score'],
                        'issues': json.loads(task['input_quality_issues'])
                    }
                except:
                    pass
            
            report['knowledge_recall_count'] = task['knowledge_recall_count']
            report['sample_saved'] = task['sample_saved']
            
        elif task['analysis_status'] in ('failed', 'low_quality'):
            report['failure_reason'] = task['failure_reason']
        
        return jsonify(report)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'service': 'wechat-callback-service',
        'version': '1.1-report-api'
    })


if __name__ == '__main__':
    print("="*60)
    print("微信机器人回调服务")
    print("="*60)
    app.run(host='0.0.0.0', port=5001, debug=False)
