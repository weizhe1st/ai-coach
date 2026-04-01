# AI Coach 知识库

## 三教练融合知识库 v3.0

### 项目简介
本项目包含三位网球教练的发球教学知识库，用于AI辅助网球教学系统。

### 教练列表

| 教练 | 知识点数 | 来源 |
|------|---------|------|
| 杨超 | 71条 | 专业网球教练 |
| 灵犀 | 41条 | 赵凌曦教练 |
| Yellow | 57条 | FuzzyYellowBalls |
| **总计** | **169条** | |

### 文件结构

```
coaches/
├── fused_knowledge/              # 融合后的知识库
│   ├── fused_knowledge_v3.json   # 完整知识库 (169条)
│   ├── fused_gold_standard_v3.json   # 金标准 (63条A级)
│   ├── fused_meta_only_v3.json   # 元数据 (21条C级)
│   └── fusion_report_v3.json     # 融合报告
├── fuzzy_yellow_knowledge/       # Yellow教练原始资料
│   ├── knowledge_base/           # 四大交付文件
│   ├── condensed_per_video/      # 视频知识点
│   └── video_meta.json           # 视频元数据
├── lingxi/                       # 灵犀教练资料
└── yangchao_coach/               # 杨超教练资料
```

### 知识库统计

#### 等级分布
- **A级（金标准）**: 63条 (37.3%)
- **B级（正常）**: 85条 (50.3%)
- **C级（元数据）**: 21条 (12.4%)

#### 阶段分布
- ready（准备）
- toss（抛球）
- loading（蓄力/奖杯姿势）
- contact（击球）
- follow（随挥）

### 生成时间
2026-04-01

### 使用说明
1. 导入数据库: 使用 `seed_coach_knowledge.py` 脚本
2. 知识召回: 根据用户问题匹配相关知识点
3. 金标准优先: 优先使用A级知识点回答

### 许可证
仅供内部使用
