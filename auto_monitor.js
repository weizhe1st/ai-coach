/**
 * 自动监控和投递系统 - 微信接收报告版本
 * 
 * 流程：微信上传视频 → 分析 → 报告发送回微信
 * 飞书仅用于程序编写和改造
 */

require('dotenv').config();
const Database = require('better-sqlite3');
const { spawn } = require('child_process');
const path = require('path');

const dbPath = process.env.DB_PATH || '/data/db/xiaolongxia_learning.db';
const db = new Database(dbPath);

// 导入微信发送模块
let wechatSender;
try {
  wechatSender = require('./wechat_sender');
} catch (e) {
  console.warn('⚠️ 微信发送模块未加载:', e.message);
}

function initTables() {
  db.exec(`CREATE TABLE IF NOT EXISTS analysis_tasks (task_id TEXT PRIMARY KEY, source_channel TEXT NOT NULL, source_user_id TEXT, video_url TEXT NOT NULL, file_name TEXT, status TEXT DEFAULT 'queued', created_at DATETIME DEFAULT CURRENT_TIMESTAMP, started_at DATETIME, completed_at DATETIME, final_report_text TEXT, clip_id TEXT, error_message TEXT)`);
  db.exec(`CREATE TABLE IF NOT EXISTS delivery_tasks (delivery_id TEXT PRIMARY KEY, task_id TEXT NOT NULL, target_channel TEXT NOT NULL, target_user_id TEXT, status TEXT DEFAULT 'queued', retry_count INTEGER DEFAULT 0, last_error TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY (task_id) REFERENCES analysis_tasks(task_id))`);
  db.exec(`CREATE TABLE IF NOT EXISTS video_uploads (upload_id TEXT PRIMARY KEY, channel TEXT NOT NULL, message_id TEXT, video_url TEXT NOT NULL, file_name TEXT, processed BOOLEAN DEFAULT 0, created_at DATETIME DEFAULT CURRENT_TIMESTAMP)`);
  console.log('✅ 数据库表初始化完成');
}

function recordUpload(channel, messageId, videoUrl, fileName) {
  const uploadId = channel + ':' + (messageId || Date.now());
  try {
    db.prepare('INSERT OR IGNORE INTO video_uploads (upload_id, channel, message_id, video_url, file_name) VALUES (?, ?, ?, ?, ?)').run(uploadId, channel, messageId, videoUrl, fileName);
    return uploadId;
  } catch (error) {
    console.error('记录上传失败:', error.message);
    return null;
  }
}

function createAnalysisTask(sourceChannel, sourceUserId, videoUrl, fileName) {
  const taskId = 'task_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  try {
    db.prepare('INSERT INTO analysis_tasks (task_id, source_channel, source_user_id, video_url, file_name, status) VALUES (?, ?, ?, ?, ?, ?)').run(taskId, sourceChannel, sourceUserId, videoUrl, fileName, 'queued');
    console.log('✅ 创建分析任务:', taskId);
    return taskId;
  } catch (error) {
    console.error('创建任务失败:', error.message);
    return null;
  }
}

function createDeliveryTask(taskId, targetChannel, targetUserId) {
  const deliveryId = 'del_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  try {
    db.prepare('INSERT INTO delivery_tasks (delivery_id, task_id, target_channel, target_user_id, status) VALUES (?, ?, ?, ?, ?)').run(deliveryId, taskId, targetChannel, targetUserId, 'queued');
    console.log('✅ 创建投递任务:', deliveryId, '->', targetChannel);
    return deliveryId;
  } catch (error) {
    console.error('创建投递任务失败:', error.message);
    return null;
  }
}

function getPendingUploads() {
  return db.prepare('SELECT * FROM video_uploads WHERE processed = 0 ORDER BY created_at ASC LIMIT 10').all();
}

function getQueuedAnalysisTasks() {
  return db.prepare('SELECT * FROM analysis_tasks WHERE status = ? ORDER BY created_at ASC LIMIT 5').all('queued');
}

function getQueuedDeliveryTasks() {
  return db.prepare('SELECT d.*, a.clip_id, a.file_name, a.video_url, a.source_user_id FROM delivery_tasks d JOIN analysis_tasks a ON d.task_id = a.task_id WHERE d.status = ? AND a.status = ? ORDER BY d.created_at ASC LIMIT 10').all('queued', 'completed');
}

function updateAnalysisTask(taskId, status, clipId, error) {
  if (status === 'processing') {
    db.prepare('UPDATE analysis_tasks SET status = ?, started_at = CURRENT_TIMESTAMP WHERE task_id = ?').run(status, taskId);
  } else if (status === 'completed') {
    db.prepare('UPDATE analysis_tasks SET status = ?, completed_at = CURRENT_TIMESTAMP, clip_id = ? WHERE task_id = ?').run(status, clipId, taskId);
  } else if (status === 'failed') {
    db.prepare('UPDATE analysis_tasks SET status = ?, error_message = ? WHERE task_id = ?').run(status, error, taskId);
  }
}

function updateDeliveryTask(deliveryId, status, error) {
  if (status === 'failed') {
    db.prepare('UPDATE delivery_tasks SET status = ?, last_error = ?, retry_count = retry_count + 1, updated_at = CURRENT_TIMESTAMP WHERE delivery_id = ?').run(status, error, deliveryId);
  } else {
    db.prepare('UPDATE delivery_tasks SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE delivery_id = ?').run(status, deliveryId);
  }
}

function markUploadProcessed(uploadId) {
  db.prepare('UPDATE video_uploads SET processed = 1 WHERE upload_id = ?').run(uploadId);
}

async function processAnalysisTask(task) {
  console.log('\n🔍 处理分析任务:', task.task_id);
  console.log('   文件:', task.file_name);
  console.log('   使用 MediaPipe 0.10+ 分析...');
  
  try {
    updateAnalysisTask(task.task_id, 'processing');
    
    // 调用新版分析脚本
    const result = await new Promise((resolve, reject) => {
      const script = path.join(__dirname, 'process_video_from_cos_v2.js');
      const child = spawn('node', [script, task.video_url, task.file_name || 'video.mp4'], { cwd: __dirname, stdio: 'pipe' });
      let output = '';
      let error = '';
      child.stdout.on('data', (data) => { output += data.toString(); process.stdout.write(data); });
      child.stderr.on('data', (data) => { error += data.toString(); process.stderr.write(data); });
      child.on('close', (code) => {
        if (code === 0) {
          const match = output.match(/ClipID:\s*([a-f0-9-]+)/i);
          resolve({ success: true, clipId: match ? match[1] : null });
        } else {
          reject(new Error(error || '进程退出码: ' + code));
        }
      });
    });

    if (result.success) {
      updateAnalysisTask(task.task_id, 'completed', result.clipId);
      console.log('✅ 分析完成:', result.clipId);
      // 只创建微信投递任务
      createDeliveryTask(task.task_id, 'wechat', task.source_user_id);
      return true;
    }
  } catch (error) {
    console.error('❌ 分析失败:', error.message);
    updateAnalysisTask(task.task_id, 'failed', null, error.message);
    return false;
  }
}

async function processDeliveryTask(task) {
  console.log('\n📤 处理投递任务:', task.delivery_id);
  console.log('   渠道:', task.target_channel);
  
  try {
    const scoring = db.prepare('SELECT * FROM clip_scoring_results WHERE clip_id = ?').get(task.clip_id);
    const score = scoring ? scoring.total_score : null;
    let bucket = '-';
    if (score >= 90) bucket = '5.0+';
    else if (score >= 80) bucket = '4.0';
    else if (score >= 62) bucket = '3.0';
    else if (score) bucket = '2.0';
    
    // 获取诊断信息
    let issues = [];
    try {
      const diagnosis = db.prepare('SELECT diagnosis_json FROM clip_diagnosis_results WHERE clip_id = ?').get(task.clip_id);
      if (diagnosis && diagnosis.diagnosis_json) {
        const diagData = JSON.parse(diagnosis.diagnosis_json);
        if (diagData.issues) {
          issues = diagData.issues.map(i => i.rule || i.description);
        }
      }
    } catch (e) {
      console.warn('⚠️  无法获取诊断信息:', e.message);
    }
    
    const report = { 
      clip_id: task.clip_id, 
      file_name: task.file_name, 
      total_score: score, 
      bucket: bucket, 
      issues: issues,
      created_at: new Date().toISOString() 
    };

    if (task.target_channel === 'wechat') {
      if (wechatSender) {
        const result = await wechatSender.sendReportToWechat(report, task.source_user_id);
        if (result.success) {
          updateDeliveryTask(task.delivery_id, 'delivered');
          console.log('✅ 投递成功: wechat (' + result.method + ')');
          return true;
        } else {
          throw new Error(result.error || '发送失败');
        }
      } else {
        console.log('⚠️ 微信发送模块未加载，输出报告到控制台');
        console.log('   报告:', JSON.stringify(report, null, 2));
        updateDeliveryTask(task.delivery_id, 'delivered');
        return true;
      }
    } else {
      throw new Error('未知渠道: ' + task.target_channel);
    }
  } catch (error) {
    console.error('❌ 投递失败:', error.message);
    updateDeliveryTask(task.delivery_id, 'failed', error.message);
    return false;
  }
}

async function processNewUploads() {
  const uploads = getPendingUploads();
  if (uploads.length === 0) return;
  console.log('\n📥 发现', uploads.length, '个新上传');
  for (const upload of uploads) {
    console.log('\n   处理:', upload.file_name || upload.video_url);
    const taskId = createAnalysisTask(upload.channel, null, upload.video_url, upload.file_name);
    if (taskId) {
      markUploadProcessed(upload.upload_id);
      console.log('   ✅ 已创建任务:', taskId);
    }
  }
}

async function monitor() {
  console.log('\n' + '='.repeat(60));
  console.log('🔍 监控检查', new Date().toISOString());
  console.log('   MediaPipe 0.10+ + 杨超教练知识点');
  console.log('   报告发送: 微信机器人');
  console.log('='.repeat(60));
  await processNewUploads();
  const analysisTasks = getQueuedAnalysisTasks();
  if (analysisTasks.length > 0) {
    console.log('\n📊 发现', analysisTasks.length, '个待分析任务');
    for (const task of analysisTasks) {
      await processAnalysisTask(task);
    }
  }
  const deliveryTasks = getQueuedDeliveryTasks();
  if (deliveryTasks.length > 0) {
    console.log('\n📤 发现', deliveryTasks.length, '个待投递任务');
    for (const task of deliveryTasks) {
      await processDeliveryTask(task);
    }
  }
  console.log('\n✅ 本轮检查完成');
}

function startMonitoring(intervalMs) {
  intervalMs = intervalMs || 60000;
  console.log('🚀 启动自动监控系统');
  console.log('   检查间隔:', intervalMs / 1000, '秒');
  console.log('   使用 MediaPipe 0.10+ 分析');
  console.log('   应用杨超教练知识点评估');
  console.log('   报告发送: 微信机器人');
  initTables();
  monitor();
  setInterval(monitor, intervalMs);
  console.log('✅ 监控系统已启动');
}

function addVideo(channel, videoUrl, fileName, messageId, sourceUserId) {
  initTables();
  const uploadId = recordUpload(channel, messageId, videoUrl, fileName);
  if (uploadId) {
    // 同时创建分析任务，包含 sourceUserId
    const taskId = createAnalysisTask(channel, sourceUserId, videoUrl, fileName);
    if (taskId) {
      console.log('✅ 已添加视频并创建分析任务:', uploadId, '->', taskId);
    } else {
      console.log('✅ 已添加视频:', uploadId);
    }
    return uploadId;
  }
  return null;
}

async function testSend() {
  if (!wechatSender) {
    console.log('❌ 微信发送模块未加载');
    return;
  }
  console.log('🧪 测试微信消息发送...');
  try {
    const result = await wechatSender.sendReportToWechat({
      clip_id: 'test-123',
      file_name: '测试视频.mp4',
      total_score: 75,
      bucket: '3.0',
      issues: ['测试问题1', '测试问题2'],
      created_at: new Date().toISOString()
    });
    console.log('✅ 测试结果:', result.method);
  } catch (error) {
    console.error('❌ 测试失败:', error.message);
  }
}

if (require.main === module) {
  const args = process.argv.slice(2);
  const command = args[0];
  if (command === 'start') {
    const interval = parseInt(args[1]) || 60000;
    startMonitoring(interval);
  } else if (command === 'add') {
    const channel = args[1];
    const videoUrl = args[2];
    const fileName = args[3];
    const messageId = args[4];
    if (!channel || !videoUrl) {
      console.log('用法: node auto_monitor.js add <channel> <video_url> [file_name] [message_id]');
      process.exit(1);
    }
    addVideo(channel, videoUrl, fileName, messageId);
  } else if (command === 'once') {
    initTables();
    monitor().then(() => process.exit(0));
  } else if (command === 'test-send') {
    testSend().then(() => process.exit(0));
  } else {
    console.log('用法:');
    console.log('  node auto_monitor.js start [interval_ms]  - 启动监控');
    console.log('  node auto_monitor.js once                 - 执行一次检查');
    console.log('  node auto_monitor.js add <channel> <url> [name] [msg_id] - 添加视频');
    console.log('  node auto_monitor.js test-send            - 测试发送');
    process.exit(1);
  }
}

module.exports = { initTables, recordUpload, createAnalysisTask, createDeliveryTask, addVideo, startMonitoring, monitor };
