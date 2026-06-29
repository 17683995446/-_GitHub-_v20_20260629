# GitCast

> 自动发现 GitHub 高价值项目 → 生成通俗中文解读 → 转化为高质量音频 → 多平台分发

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

## 快速开始

```bash
# 安装依赖
make dev

# 复制环境变量模板
cp .env.example .env
# 编辑 .env 填入真实密钥

# 运行
make run
```

## 架构

```
[发现层]  GitHub Search API + Trending 爬虫 + starpulse 增长监控
    ↓
[文档层]  Repomix 打包仓库 → DeepSeek/Qwen LLM 生成通俗文章
    ↓
[音频层]  CosyVoice2 自托管 / Azure TTS 云端
    ↓
[发布层]  喜马拉雅 / 小宇宙 / B站 / 微信公众号
    ↓
[编排层]  n8n 自托管 + GitHub Actions 定时触发
```

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.11+ / FastAPI / SQLAlchemy 2.0 |
| 数据库 | PostgreSQL 16 / Redis 7 |
| LLM | Qwen2.5-72B (SiliconFlow) |
| TTS | Azure TTS / CosyVoice2 |
| 编排 | n8n / GitHub Actions |
| 部署 | Docker / Docker Compose |

## 项目结构

```
gitcast/
├── services/          # 业务服务层
│   ├── discovery/     # GitHub 项目发现
│   ├── generator/     # LLM 文档生成
│   ├── tts/           # TTS 音频合成
│   ├── publisher/     # 多平台发布
│   └── api/           # Web 后台 API
├── models/            # 数据模型
├── shared/            # 公共库（配置、日志、错误）
├── prompts/           # LLM Prompt 模板
├── workflows/         # n8n 工作流定义
├── tests/             # 测试
├── deploy/            # 部署配置
└── docs/              # 文档
```

## License

MIT
