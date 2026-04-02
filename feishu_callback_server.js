/**
 * 飞书事件回调服务器
 * 只保留查询功能，不处理视频分析
 */

const http = require('http');
const crypto = require('crypto');
const sqlite3 = require('better-sqlite3');

// 飞书配置
const FEISHU_APP_ID = process.env.FEISHU_APP_ID || 'cli_a94e5d45e7395cc8';
const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || '9F5mb37LszE17WrEf0N9igzHRzwunF04';
const FEISHU_VERIFICATION_TOKEN = process.env.FEISHU_VERIFICATION_TOKEN || '';

// 数据库配置
const DB_PATH = '/data/db/xiaolongxia_learning.db';

/**
 * 查询视频分析结果
 */
function queryVideoResult(videoId) {
  try {
    const db = sqlite3(DB_PATH);
    db.pragma('journal_mode = WAL');
    
    const result = db.prepare(`
      SELECT 
        t.id,
        t.video_id,
        t.ntrp_level,
        t.ntrp_confidence,
        t.analysis_status,
        t.analysis_result,
        t.created_at,
        m.corrected_level as manual_level
      FROM video_analysis_tasks t
      LEFT JOIN manual_corrections m ON t.id = m.task_id
      WHERE t.video_id = ?
      ORDER BY t.created_at DESC
      LIMIT 1
    `).get(videoId);
    
    db.close();
    
    if (!result) {
      return null;
    }
    
    // 解析analysis_result
    let details = {};
    if (result.analysis_result) {
      try {
        const parsed = JSON.parse(result.analysis_result);
        details = {
          level_scores: parsed.ntrp_evaluation?.details?.level_scores,
          metrics: parsed.ntrp_evaluation?.details?.metrics,
          knowledge_count: parsed.knowledge_recall_summary?.total_recalled
        };
      } catch (e) {
        console.log('解析analysis_result失败:', e.message);
      }
    }
    
    return {
      task_id: result.id,
      video_id: result.video_id,
      system_level: result.ntrp_level,
      manual_level: result.manual_level,
      final_level: result.manual_level || result.ntrp_level,
      confidence: result.ntrp_confidence,
      status: result.analysis_status,
      created_at: result.created_at,
      details: details
    };
    
  } catch (error) {
    console.error('查询数据库失败:', error.message);
    return null;
  }
}

/**
 * 验证飞书请求签名
 */
function verifySignature(timestamp, nonce, body, signature) {
  if (!FEISHU_VERIFICATION_TOKEN) return true;
  
  const content = timestamp + nonce + FEISHU_VERIFICATION_TOKEN + body;
  const hash = crypto.createHash('sha256').update(content).digest('hex');
  return hash === signature;
}

/**
 * 处理飞书事件
 */
async function handleFeishuEvent(event) {
  console.log('📨 收到飞书事件:', event.header?.event_type || event.type);
  
  const eventType = event.header?.event_type || event.type;
  
  switch (eventType) {
    case 'url_verification':
      return { challenge: event.challenge };
      
    case 'im.message.receive_v1':
      return await handleMessageEvent(event.event);
      
    default:
      console.log('ℹ️  未处理的事件类型:', eventType);
      return { code: 0 };
  }
}

/**
 * 处理文本消息事件
 */
async function handleMessageEvent(event) {
  const message = event.message;
  const sender = event.sender;
  
  console.log('💬 收到消息:');
  console.log('   发送者:', sender.sender_id?.open_id);
  console.log('   消息类型:', message.message_type);
  
  // 解析消息内容
  let content;
  try {
    content = JSON.parse(message.content);
  } catch (e) {
    content = { text: message.content };
  }
  
  const text = content.text || '';
  
  // 检查是否是视频查询命令
  if (text.includes('查询') || text.includes('查视频') || text.includes('分析结果')) {
    // 尝试提取video_id
    const videoIdMatch = text.match(/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}/);
    
    if (videoIdMatch) {
      const videoId = videoIdMatch[0];
      console.log('🔍 查询视频:', videoId);
      
      const result = queryVideoResult(videoId);
      
      if (result) {
        let responseText = `🎾 视频分析结果\n\n`;
        responseText += `视频ID: ${result.video_id}\n`;
        responseText += `状态: ${result.status}\n`;
        
        if (result.final_level) {
          responseText += `\n🏆 NTRP等级: ${result.final_level}\n`;
          if (result.manual_level) {
            responseText += `   (系统: ${result.system_level} → 人工修正: ${result.manual_level})\n`;
          }
          responseText += `置信度: ${result.confidence || 'N/A'}\n`;
        }
        
        if (result.details && result.details.knowledge_count) {
          responseText += `知识召回: ${result.details.knowledge_count}条\n`;
        }
        
        responseText += `\n分析时间: ${result.created_at}\n`;
        
        await sendFeishuMessage(sender.sender_id?.open_id, responseText);
      } else {
        await sendFeishuMessage(
          sender.sender_id?.open_id,
          `⚠️ 未找到视频 ${videoId} 的分析结果\n\n该视频还没有分析，请通过微信上传视频获取分析。`
        );
      }
    } else {
      await sendFeishuMessage(
        sender.sender_id?.open_id,
        `🎾 视频查询服务\n\n请提供视频ID进行查询，格式：\n查询视频 [video_id]\n\n例如：\n查询视频 92bb38d2-8031-4229-81f8-645abbc45ea7`
      );
    }
    
    return { code: 0 };
  }
  
  // 其他消息，回复功能说明
  if (text.includes('帮助') || text.includes('功能') || text.includes('help')) {
    await sendFeishuMessage(
      sender.sender_id?.open_id,
      `🎾 飞书机器人功能\n\n📊 查询服务：\n• 查询视频 [video_id] - 查询分析结果\n\n⚠️ 注意：\n飞书只提供查询服务，不处理视频分析。\n\n📱 如需分析视频，请通过微信上传。`
    );
    return { code: 0 };
  }
  
  return { code: 0 };
}

/**
 * 发送飞书消息
 */
async function sendFeishuMessage(openId, text) {
  console.log('📤 发送消息给:', openId);
  console.log('   内容:', text.substring(0, 100) + '...');
  // 实际实现需要调用飞书API
}

/**
 * 创建 HTTP 服务器
 */
function createServer(port = 3000) {
  const server = http.createServer(async (req, res) => {
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    if (req.method === 'OPTIONS') {
      res.writeHead(200);
      res.end();
      return;
    }
    
    if (req.method !== 'POST') {
      res.writeHead(405, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ code: 405, message: 'Method Not Allowed' }));
      return;
    }
    
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', async () => {
      try {
        console.log('\n📥 收到请求:', req.url);
        
        const timestamp = req.headers['x-lark-request-timestamp'];
        const nonce = req.headers['x-lark-request-nonce'];
        const signature = req.headers['x-lark-signature'];
        
        if (!verifySignature(timestamp, nonce, body, signature)) {
          console.error('❌ 签名验证失败');
          res.writeHead(401, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ code: 401, message: 'Unauthorized' }));
          return;
        }
        
        const event = JSON.parse(body);
        const result = await handleFeishuEvent(event);
        
        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify(result));
        
      } catch (error) {
        console.error('❌ 处理请求失败:', error.message);
        res.writeHead(500, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ code: 500, message: error.message }));
      }
    });
  });
  
  server.listen(port, () => {
    console.log('='.repeat(60));
    console.log('🚀 飞书回调服务器已启动（仅查询模式）');
    console.log('   端口:', port);
    console.log('='.repeat(60));
    console.log('\n📋 功能：');
    console.log('   1. 查询视频分析结果');
    console.log('   2. 不处理视频上传/分析');
    console.log('\n⚠️  视频分析请使用微信');
  });
  
  return server;
}

// 启动服务器
const PORT = process.env.FEISHU_CALLBACK_PORT || 3000;
createServer(PORT);

module.exports = { createServer, handleFeishuEvent, queryVideoResult };
