#!/usr/bin/env node
/**
 * 独立分析 Worker 服务
 * 从数据库队列获取任务，避免阻塞飞书主进程
 */

require('dotenv').config();
const Database = require('better-sqlite3');
const { spawn } = require('child_process');
const path = require('path');

const dbPath = process.env.DB_PATH || '/data/db/xiaolongxia_learning.db';
const db = new Database(dbPath);
const RUNNING = true;

// 初始化数据库表
function initTables() {
  db.exec(`
    CREATE TABLE IF NOT EXISTS analysis_tasks (
      task_id TEXT PRIMARY KEY,
      source_channel TEXT NOT NULL,
      source_user_id TEXT,
      video_url TEXT NOT NULL,
      file_name TEXT,
      status TEXT DEFAULT 'queued',
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
      started_at DATETIME,
      completed_at DATETIME,
      clip_id TEXT,
      error_message TEXT
    )
  `);
  console.log('✅ Worker 数据库表初始化完成');
}

// 获取待处理任务
function getPendingTask() {
  return db.prepare(
    "SELECT * FROM analysis_tasks WHERE status = 'queued' ORDER BY created_at ASC LIMIT 1"
  ).get();
}

// 更新任务状态
function updateTaskStatus(taskId, status, clipId = null, error = null) {
  if (status === 'processing') {
    db.prepare("UPDATE analysis_tasks SET status = ?, started_at = CURRENT_TIMESTAMP WHERE task_id = ?")
      .run(status, taskId);
  } else if (status === 'completed') {
    db.prepare("UPDATE analysis_tasks SET status = ?, completed_at = CURRENT_TIMESTAMP, clip_id = ? WHERE task_id = ?")
      .run(status, clipId, taskId);
  } else if (status === 'failed') {
    db.prepare("UPDATE analysis_tasks SET status = ?, error_message = ? WHERE task_id = ?")
      .run(status, error, taskId);
  }
}

// 创建投递任务
function createDeliveryTask(taskId, targetChannel, targetUserId) {
  const deliveryId = 'del_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
  try {
    db.prepare(`
      INSERT INTO delivery_tasks (delivery_id, task_id, target_channel, target_user_id, status)
      VALUES (?, ?, ?, ?, ?)
    `).run(deliveryId, taskId, targetChannel, targetUserId, 'queued');
    console.log('✅ 创建投递任务:', deliveryId);
    return deliveryId;
  } catch (error) {
    console.error('❌ 创建投递任务失败:', error.message);
    return null;
  }
}

// 处理单个任务
async function processTask(task) {
  console.log('\n🔍 处理分析任务:', task.task_id);
  console.log('   文件:', task.file_name);
  
  try {
    updateTaskStatus(task.task_id, 'processing');
    
    // 使用异步 spawn 代替 execSync，避免阻塞
    const result = await new Promise((resolve, reject) => {
      const script = path.join(__dirname, 'process_video_from_cos_v2.js');
      const child = spawn('node', [script, task.video_url, task.file_name || 'video.mp4'], {
        cwd: __dirname,
        stdio: 'pipe',
        detached: false // 不分离，保持控制
      });
      
      let output = '';
      let error = '';
      let killed = false;
      
      // 设置超时保护
      const timeout = setTimeout(() => {
        killed = true;
        child.kill('SIGTERM');
        reject(new Error('分析超时(10分钟)'));
      }, 600000);
      
      child.stdout.on('data', (data) => {
        output += data.toString();
        process.stdout.write(data);
      });
      
      child.stderr.on('data', (data) => {
        error += data.toString();
        process.stderr.write(data);
      });
      
      child.on('close', (code) => {
        clearTimeout(timeout);
        if (killed) return; // 已处理超时
        
        if (code === 0) {
          const match = output.match(/ClipID:\s*([a-f0-9-]+)/i);
          resolve({ success: true, clipId: match ? match[1] : null });
        } else {
          reject(new Error(error || `进程退出码: ${code}`));
        }
      });
      
      child.on('error', (err) => {
        clearTimeout(timeout);
        reject(err);
      });
    });
    
    if (result.success) {
      updateTaskStatus(task.task_id, 'completed', result.clipId);
      console.log('✅ 分析完成:', result.clipId);
      
      // 创建投递任务
      if (task.source_channel === 'wechat' || task.source_channel === 'feishu') {
        createDeliveryTask(task.task_id, task.source_channel, task.source_user_id);
      }
      return true;
    }
  } catch (error) {
    console.error('❌ 分析失败:', error.message);
    updateTaskStatus(task.task_id, 'failed', null, error.message);
    return false;
  }
}

// Worker 主循环
async function workerLoop() {
  console.log('\n' + '='.repeat(60));
  console.log('🚀 独立分析 Worker 启动');
  console.log('   数据库:', dbPath);
  console.log('   轮询间隔: 5秒');
  console.log('='.repeat(60));
  
  initTables();
  
  while (RUNNING) {
    try {
      const task = getPendingTask();
      
      if (task) {
        await processTask(task);
      } else {
        // 没有任务，等待5秒
        await new Promise(resolve => setTimeout(resolve, 5000));
      }
    } catch (error) {
      console.error('❌ Worker 循环错误:', error.message);
      await new Promise(resolve => setTimeout(resolve, 10000)); // 出错后等待10秒
    }
  }
}

// 启动 Worker
workerLoop().catch(console.error);

// 优雅退出
process.on('SIGTERM', () => {
  console.log('\n👋 Worker 收到退出信号');
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('\n👋 Worker 收到中断信号');
  process.exit(0);
});
