#!/usr/bin/env python3
"""
微信视频分析 Webhook 服务
包装 weixin_handler.py 提供HTTP接口
"""

import os
import sys
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 导入微信消息处理器
sys.path.insert(0, '/data/apps/xiaolongxia')
from weixin_handler import handle_weixin_message

app = Flask(__name__)

@app.route('/health', methods=['GET'])
def health():
    """健康检查"""
    return jsonify({
        'status': 'ok',
        'service': 'weixin-webhook-service',
        'version': '1.0',
        'timestamp': datetime.now().isoformat()
    })

@app.route('/wechat/video', methods=['POST'])
def handle_video():
    """处理微信视频消息"""
    try:
        # 获取请求数据
        data = request.get_json() or request.form.to_dict()
        
        logger.info("[Webhook] 收到视频消息: %s", data.get('FromUserName', 'unknown'))
        logger.info("[Webhook] VideoUrl: %s...", data.get('VideoUrl', 'N/A')[:60])
        
        # 调用处理器
        result = handle_weixin_message(data)
        
        logger.info("[Webhook] 处理完成，返回结果长度: %d", len(result))
        
        return jsonify({
            'success': True,
            'reply': result,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error("[Webhook] 处理失败: %s", e)
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 500

@app.route('/wechat/message', methods=['POST'])
def handle_message():
    """处理通用微信消息"""
    try:
        data = request.get_json() or request.form.to_dict()
        
        msg_type = data.get('MsgType', '')
        user_id = data.get('FromUserName', '')
        
        logger.info("[Webhook] 收到消息: type=%s, user=%s", msg_type, user_id)
        
        # 调用处理器
        result = handle_weixin_message(data)
        
        return jsonify({
            'success': True,
            'reply': result,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        logger.error("[Webhook] 处理失败: %s", e)
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

if __name__ == '__main__':
    # 检查API密钥环境变量
    if not os.environ.get('MOONSHOT_API_KEY'):
        logger.error("[Init] 错误: 未设置 MOONSHOT_API_KEY 环境变量")
        sys.exit(1)
    logger.info("[Init] MOONSHOT_API_KEY 已配置")
    
    port = int(os.environ.get('WEBHOOK_PORT', 5002))
    
    print("="*60)
    print("微信视频分析 Webhook 服务")
    print("="*60)
    print("端口: %d" % port)
    print("接口: POST /wechat/video")
    print("健康: GET  /health")
    print("="*60)
    
    app.run(host='0.0.0.0', port=port, debug=False, threaded=True)
