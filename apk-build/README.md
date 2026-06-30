# GitCast APK 云端构建

## 不用电脑，手机浏览器即可生成 APK

### 方法：GitHub Actions 云端构建（推荐）

代码已推送到 GitHub，GitHub 提供免费的云端构建服务。

#### 步骤（手机浏览器操作）

1. **打开 GitHub**
   手机浏览器访问你的仓库：`https://github.com/17683995446/-_GitHub-_v20_20260629`

2. **进入 Actions 页面**
   点击顶部 **Actions** 标签

3. **选择工作流**
   左侧找到 **Build Android APK** 工作流

4. **手动触发构建**
   点击右侧 **Run workflow** 按钮 → 选择 `main` 分支 → 点击绿色 **Run workflow** 按钮

5. **等待构建完成**
   构建约需 5-10 分钟。点击进入构建详情可查看实时日志。

6. **下载 APK**
   构建完成后，在页面底部 **Artifacts** 区域找到 **GitCast-APK**，点击下载即可得到 `GitCast.apk`

7. **安装 APK**
   下载后点击安装（可能需要在手机设置中允许"安装未知来源应用"）

#### APK 首次使用

1. 安装后打开 GitCast
2. 进入「使用指南」页面
3. 在「服务器设置」中输入后端地址（如 `http://192.168.1.100:8000`）
4. 点击「测试连接」→「保存」

---

### 其他在线构建方案（备选）

| 服务 | 网址 | 说明 |
|------|------|------|
| AppsGeyser | https://appsgeyser.com | 输入网址免费生成 APK |
| FreeWebToAPK | https://freewebtoapk.com | PWA 转 APK，支持 TWA |
| AppyPie | https://www.appypie.com/convert-website-to-apk | 网站转 APK |
| Replit | https://replit.com/build/website-to-apk-builder | AI 辅助构建 |

> 注意：以上在线服务需要你的 GitCast 有公网可访问的 HTTPS 地址，适用于已部署到云服务器的场景。
