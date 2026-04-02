/**
 * 飞书事件回调服务器
 * 接收飞书长连接回调，处理视频上传事件
 */

const http = require('http');
const crypto = require('crypto');
const url = require('url');

// 飞书配置
const FEISHU_APP_ID = process.env.FEISHU_APP_ID || 'cli_a94e5d45e7395cc8';
const FEISHU_APP_SECRET = process.env.FEISHU_APP_SECRET || '9F5mb37LszE17WrEf0N9igzHRzwunF04';
const FEISHU_ENCRYPT_KEY = process.env.FEISHU_ENCRYPT_KEY || ''; // 如果启用了加密
const FEISHU_VERIFICATION_TOKEN = process.env.FEISHU_VERIFICATION_TOKEN || ''; // 验证 Token

// 导入监控模块
const { addVideo, initTables } = require('./auto_monitor');

// 初始化数据库
initTables();

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
 * 解密飞书消息（如果启用了加密）
 */
function decryptMessage(encrypt) {
  if (!FEISHU_ENCRYPT_KEY || !encrypt) return encrypt;
  
  // 简化解密，实际需要实现完整的 AES-256-CBC 解密
  console.log('⚠️ 消息加密已启用，但未实现解密逻辑');
  return encrypt;
}

/**
 * 处理飞书事件
 */
async function handleFeishuEvent(event) {
  console.log('📨 收到飞书事件:', event.header?.event_type || event.type);
  
  const eventType = event.header?.event_type || event.type;
  
  switch (eventType) {
    case 'url_verification':
      // 验证 URL
      return { challenge: event.challenge };
      
    case 'im.message.receive_v1':
      // 收到消息
      return await handleMessageEvent(event.event);
      
    case 'im.message.file.receive_v1':
      // 收到文件消息
      return await handleFileMessageEvent(event.event);
      
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
  console.log('   内容:', message.content);
  
  // 解析消息内容
  let content;
  try {
    content = JSON.parse(message.content);
  } catch (e) {
    content = { text: message.content };
  }
  
  // 检查是否是视频上传命令
  const text = content.text || '';
  if (text.includes('分析视频') || text.includes('上传视频')) {
    // 回复用户
    return {
      code: 0,
      message: '请直接上传视频文件，系统将自动分析'
    };
  }
  
  return { code: 0 };
}

/**
 * 处理文件消息事件（视频文件）
 * ⚠️ 飞书不参与视频分析，引导用户到微信
 */
async function handleFileMessageEvent(event) {
  const message = event.message;
  const sender = event.sender;
  
  console.log('📹 收到文件消息:');
  console.log('   发送者:', sender.sender_id?.open_id);
  console.log('   文件类型:', message.message_type);
  
  if (message.message_type === 'video') {
    console.log('   ⚠️ 飞书不处理视频分析，引导用户到微信');
    
    // 回复用户，引导到微信
    try {
      await sendFeishuMessage(
        sender.sender_id?.open_id, 
        `🎾 视频分析服务\n\n请通过微信上传视频获取分析报告。\n\n飞书机器人负责：\n• 代码开发和部署\n• 系统监控和日志\n• 数据库维护\n\n微信机器人负责：\n• 接收发球视频\n• 生成分析报告\n• 回答技术问题`
      );
      console.log('✅ 已回复用户，引导到微信');
    } catch (sendError) {
      console.error('❌ 发送消息失败:', sendError.message);
    }
  }
  
  return { code: 0 };
}

/**
 * 获取视频下载链接
 */
async function getVideoDownloadUrl(fileKey) {
  // 这里需要调用飞书 API 获取下载链接
  // 简化处理，实际实现需要调用 open-apis/im/v1/files/{file_key}
  console.log('⚠️ 需要实现获取视频下载链接逻辑');
  console.log('   FileKey:', fileKey);
  return null;
}

/**
 * 发送飞书消息
 */
async function sendFeishuMessage(openId, text) {
  // 这里需要调用飞书 API 发送消息
  // 简化处理，实际实现需要调用 open-apis/im/v1/messages
  console.log('📤 发送消息给:', openId);
  console.log('   内容:', text);
}

/**
 * 创建 HTTP 服务器
 */
function createServer(port = 3000) {
  const server = http.createServer(async (req, res) => {
    // 设置 CORS 头
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    
    if (req.method === 'OPTIONS') {
      res.writeHead(200);
      res.end();
      return;
    }
    
    // 只处理 POST 请求
    if (req.method !== 'POST') {
      res.writeHead(405, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ code: 405, message: 'Method Not Allowed' }));
      return;
    }
    
    // 读取请求体
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', async () => {
      try {
        console.log('\n📥 收到请求:', req.url);
        console.log('   时间:', new Date().toISOString());
        
        // 获取签名信息
        const timestamp = req.headers['x-lark-request-timestamp'];
        const nonce = req.headers['x-lark-request-nonce'];
        const signature = req.headers['x-lark-signature'];
        
        // 验证签名
        if (!verifySignature(timestamp, nonce, body, signature)) {
          console.error('❌ 签名验证失败');
          res.writeHead(401, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ code: 401, message: 'Unauthorized' }));
          return;
        }
        
        // 解析事件
        const event = JSON.parse(body);
        
        // 处理事件
        const result = await handleFeishuEvent(event);
        
        // 返回响应
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
    console.log('🚀 飞书事件回调服务器已启动');
    console.log('   端口:', port);
    console.log('   地址: http://0.0.0.0:' + port);
    console.log('='.repeat(60));
    console.log('\n📋 使用说明:');
    console.log('   1. 在飞书开发者平台配置事件订阅 URL');
    console.log('   2. 订阅 im.message.receive_v1 事件');
    console.log('   3. 上传视频文件到飞书群');
    console.log('   4. 系统将自动接收并分析视频');
    console.log('\n⚠️  注意:');
    console.log('   需要将服务器暴露到公网，飞书才能访问');
    console.log('   可以使用 ngrok 或配置公网 IP');
  });
  
  return server;
}

// 启动服务器
const PORT = process.env.FEISHU_CALLBACK_PORT || 3000;
createServer(PORT);

module.exports = { createServer, handleFeishuEvent };
