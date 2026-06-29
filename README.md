# GitCast · GitHub 项目播客工厂

> 自动发现 GitHub 热门项目 → AI 深度解读 → TTS 播客合成 → 一键发布到全平台

**版本**：v22 · 2026-06-29

## 🎬 在线预览

可视化项目介绍网站已部署到 GitHub Pages：

**🔗 https://17683995446.github.io/-_GitHub-_v20_20260629/preview/**

> 键盘控制：`→` / `Space` / `Enter` 下一张，`←` 上一张，`F` 全屏

## ✨ 核心亮点

| 能力 | 详情 |
|------|------|
| 🔍 **发现项目** | GitHub Trending + Search API 分页，最高 1000 个仓库 |
| 🤖 **AI 写作** | 硅基流动 Qwen-72B，800-1200 字/篇，深度解读 |
| 🎤 **TTS 播客** | CosyVoice2 8 种音色，FFmpeg 响度标准化 |
| ⚡ **批量生成** | 1 串行 / 2 / 5 / 8 / 10 路并发可调 |
| 📊 **实时进度** | 完成度百分比 + 当前处理项目名实时显示 |
| 🔁 **连续播放** | 当前文章播完自动播放下一篇 |
| 💾 **本地持久化** | 历史文章 + 偏好设置保存到 localStorage |

## 📦 项目结构

```
.
├── api/                # FastAPI 后端（批量生成、TTS、任务调度）
├── services/           # 业务服务（GitHub 发现、内容生成）
├── shared/             # 配置、日志、数据库连接
├── console/            # GitCast 控制台前端（生产用）
├── preview/            # 项目可视化介绍站点（GitHub Pages）
└── docs/               # 项目架构文档
```

## 🏗 技术栈

- **后端**：FastAPI + asyncpg + httpx
- **AI**：SiliconFlow Qwen-72B / CosyVoice2 TTS
- **前端**：原生 JavaScript + Howler.js + ECharts
- **基础设施**：FFmpeg · Redis · PostgreSQL · Docker

## 🚀 快速开始

```bash
# 后端
cd api && pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000

# 前端控制台
cd console && python -m http.server 8080
```

## 📜 版本演进

| 版本 | 关键能力 | 批量上限 | 并发 |
|------|----------|----------|------|
| v19 | 音量增强（服务端 loudnorm） | 10 | 3 |
| v20 | 连续播放 | 10 | 3 |
| v21 | 实时进度 + 流式结果 | 30 | 5 |
| **v22** | **1000 篇上限 + 串行模式** | **1000** | **1-10** |

---

Made with ❤️ by 开发者工具 · 2026
