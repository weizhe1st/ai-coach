#!/usr/bin/env node
/**
 * 视频处理脚本 - 调用 weixin_video_service.py 生成完整报告
 * 包含：MediaPipe + Kimi K2.5 + 知识库 + 样本库
 */

const { spawn } = require('child_process');
const path = require('path');

// 调用 weixin_video_service.py
async function analyzeVideo(videoUrl, fileName) {
  return new Promise((resolve, reject) => {
    // 先下载视频到临时文件
    const tmpFile = `/tmp/video_${Date.now()}.mp4`;
    
    // 使用 curl 下载视频
    const download = spawn('curl', ['-s', '-o', tmpFile, videoUrl], {
      stdio: 'pipe'
    });
    
    download.on('close', (code) => {
      if (code !== 0) {
        reject(new Error('下载视频失败'));
        return;
      }
      
      console.log('📥 视频下载完成:', tmpFile);
      
      // 调用 weixin_video_service.py 分析
      const script = path.join(__dirname, 'weixin_video_service.py');
      const child = spawn('python3', [script, tmpFile, '--user-id', 'wechat_bot'], {
        cwd: __dirname,
        stdio: 'pipe',
        env: {
          ...process.env,
          'MOONSHOT_API_KEY': 'sk-LsZC9HAarYmH6oH4EkOzCEhIIUZ02yvsU6J7xr1u26iifksq',
          'PYTHONPATH': __dirname
        }
      });
      
      let output = '';
      let error = '';
      
      child.stdout.on('data', (data) => {
        output += data.toString();
        process.stdout.write(data);
      });
      
      child.stderr.on('data', (data) => {
        error += data.toString();
        process.stderr.write(data);
      });
      
      child.on('close', (exitCode) => {
        // 清理临时文件
        try {
          require('fs').unlinkSync(tmpFile);
        } catch (e) {}
        
        if (exitCode === 0) {
          resolve({
            success: true,
            output: output,
            report: output  // weixin_video_service.py 直接输出报告
          });
        } else {
          reject(new Error(error || '分析失败，退出码: ' + exitCode));
        }
      });
    });
  });
}

// 主函数
async function main() {
  const videoUrl = process.argv[2];
  const fileName = process.argv[3] || 'video.mp4';

  if (!videoUrl) {
    console.error('用法: node process_video_from_cos_v2.js <video_url> [file_name]');
    process.exit(1);
  }

  console.log('🎾 开始完整分析流程...');
  console.log('   URL:', videoUrl.substring(0, 80) + '...');
  console.log('   文件名:', fileName);
  console.log('   包含: MediaPipe + Kimi K2.5 + 知识库 + 样本库');
  console.log('');

  try {
    const result = await analyzeVideo(videoUrl, fileName);
    
    if (result.success) {
      console.log('\n✅ 分析完成');
      
      // 生成 clip_id
      const clipId = 'clip_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
      console.log('ClipID:', clipId);
      process.exit(0);
    } else {
      throw new Error('分析结果异常');
    }
  } catch (error) {
    console.error('\n❌ 分析失败:', error.message);
    process.exit(1);
  }
}

main();
