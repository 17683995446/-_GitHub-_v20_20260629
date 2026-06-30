/**
 * GitCast 全功能前端引擎
 * 将后端的 quickgen + TTS 逻辑完全搬到前端，APK 无需后端服务器
 *
 * 调用的外部 API：
 * - GitHub REST API (支持 CORS)
 * - SiliconFlow LLM API (Capacitor HTTP 插件绕过 CORS)
 * - SiliconFlow TTS API (Capacitor HTTP 插件绕过 CORS)
 */
(function(global) {
  'use strict';

  // ===== 配置 =====
  var VOICES = {
    alex: { name: '沉稳男声', id: 'FunAudioLLM/CosyVoice2-0.5B:alex' },
    benjamin: { name: '低沉男声', id: 'FunAudioLLM/CosyVoice2-0.5B:benjamin' },
    charles: { name: '磁性男声', id: 'FunAudioLLM/CosyVoice2-0.5B:charles' },
    david: { name: '欢快男声', id: 'FunAudioLLM/CosyVoice2-0.5B:david' },
    anna: { name: '沉稳女声', id: 'FunAudioLLM/CosyVoice2-0.5B:anna' },
    bella: { name: '激情女声', id: 'FunAudioLLM/CosyVoice2-0.5B:bella' },
    claire: { name: '温柔女声', id: 'FunAudioLLM/CosyVoice2-0.5B:claire' },
    diana: { name: '欢快女声', id: 'FunAudioLLM/CosyVoice2-0.5B:diana' }
  };

  var DEFAULTS = {
    llmApiBase: 'https://api.siliconflow.cn/v1',
    llmModel: 'Qwen/Qwen2.5-72B-Instruct',
    ttsModel: 'FunAudioLLM/CosyVoice2-0.5B',
    githubApiBase: 'https://api.github.com'
  };

  // ===== Capacitor HTTP 插件（绕过 CORS）=====
  // Capacitor 6+ 内置 HTTP 插件，在 capacitor.config.json 中启用
  var CapacitorHttp = null;
  try {
    if (typeof Capacitor !== 'undefined' && Capacitor.Plugins) {
      CapacitorHttp = Capacitor.Plugins.CapacitorHttp || Capacitor.Plugins.Http;
    }
  } catch(e) {}

  // 检测是否在 Capacitor APK 中运行
  var isCapacitor = false;
  try {
    isCapacitor = (typeof Capacitor !== 'undefined' && Capacitor.isNative);
  } catch(e) {}

  /**
   * 统一 HTTP 请求函数
   * 优先使用 Capacitor HTTP 插件（绕过 CORS），否则用 fetch
   */
  async function http(options) {
    var method = (options.method || 'GET').toUpperCase();
    var headers = options.headers || {};
    var body = options.json ? JSON.stringify(options.json) : (options.body || null);

    if (body && method !== 'GET') {
      headers['Content-Type'] = headers['Content-Type'] || 'application/json';
    }

    // 优先使用 Capacitor HTTP 插件（APK 模式，无 CORS 限制）
    if (CapacitorHttp) {
      var opts = {
        url: options.url,
        method: method,
        headers: headers
      };
      if (body) opts.data = body;
      if (options.responseType === 'blob') {
        opts.responseType = 'arraybuffer';
      }
      var resp = await CapacitorHttp.request(opts);
      if (options.responseType === 'blob') {
        // Capacitor 返回 base64
        if (resp.data && typeof resp.data === 'string') {
          var binary = atob(resp.data);
          var bytes = new Uint8Array(binary.length);
          for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
          return { ok: resp.status >= 200 && resp.status < 300, status: resp.status, data: bytes.buffer };
        }
        return { ok: resp.status >= 200 && resp.status < 300, status: resp.status, data: resp.data };
      }
      var jsonData = resp.data;
      if (typeof jsonData === 'string') {
        try { jsonData = JSON.parse(jsonData); } catch(e) {}
      }
      return { ok: resp.status >= 200 && resp.status < 300, status: resp.status, json: jsonData, text: typeof resp.data === 'string' ? resp.data : JSON.stringify(resp.data) };
    }

    // 回退到 fetch（PWA / 浏览器模式，受 CORS 限制）
    var fetchResp = await fetch(options.url, {
      method: method,
      headers: headers,
      body: body || undefined
    });

    if (options.responseType === 'blob') {
      var buf = await fetchResp.arrayBuffer();
      return { ok: fetchResp.ok, status: fetchResp.status, data: buf };
    }

    var text = await fetchResp.text();
    var parsed = null;
    try { parsed = JSON.parse(text); } catch(e) {}
    return { ok: fetchResp.ok, status: fetchResp.status, json: parsed, text: text };
  }

  // ===== API Key 管理 =====
  function getKeys() {
    try {
      return {
        githubToken: localStorage.getItem('gc_github_token') || '',
        llmApiKey: localStorage.getItem('gc_llm_api_key') || '',
        llmApiBase: localStorage.getItem('gc_llm_api_base') || DEFAULTS.llmApiBase,
        llmModel: localStorage.getItem('gc_llm_model') || DEFAULTS.llmModel
      };
    } catch(e) {
      return { githubToken: '', llmApiKey: '', llmApiBase: DEFAULTS.llmApiBase, llmModel: DEFAULTS.llmModel };
    }
  }

  function saveKeys(keys) {
    try {
      localStorage.setItem('gc_github_token', keys.githubToken || '');
      localStorage.setItem('gc_llm_api_key', keys.llmApiKey || '');
      localStorage.setItem('gc_llm_api_base', keys.llmApiBase || DEFAULTS.llmApiBase);
      localStorage.setItem('gc_llm_model', keys.llmModel || DEFAULTS.llmModel);
    } catch(e) {}
  }

  function hasKeys() {
    var k = getKeys();
    return !!(k.llmApiKey);
  }

  // ===== 1. 发现 GitHub 项目 =====
  async function discoverRepos(language, count, onProgress) {
    var keys = getKeys();
    var headers = {
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'GitCast/1.0'
    };
    if (keys.githubToken) {
      headers['Authorization'] = 'token ' + keys.githubToken;
    }

    var langFilter = language ? 'language:' + language : 'stars:>100';
    var query = langFilter + ' stars:>50 pushed:>2025-01-01';
    var perPage = Math.min(100, count);
    var pagesNeeded = Math.min(Math.ceil(count / perPage), 10);

    var repos = [];
    var seen = {};

    for (var page = 1; page <= pagesNeeded; page++) {
      if (repos.length >= count) break;

      var url = DEFAULTS.githubApiBase + '/search/repositories' +
        '?q=' + encodeURIComponent(query) +
        '&sort=stars&order=desc' +
        '&per_page=' + perPage +
        '&page=' + page;

      if (onProgress) onProgress('正在搜索第 ' + page + ' 页项目...');

      try {
        var resp = await http({ url: url, headers: headers });
        if (!resp.ok || !resp.json) break;

        var items = resp.json.items || [];
        if (items.length === 0) break;

        for (var i = 0; i < items.length; i++) {
          var item = items[i];
          var fullName = item.full_name;
          if (!fullName || seen[fullName]) continue;
          seen[fullName] = true;
          repos.push({
            full_name: fullName,
            description: item.description || '',
            stars_today: item.stargazers_count || 0,
            repo_url: item.html_url || ('https://github.com/' + fullName),
            language: item.language || ''
          });
          if (repos.length >= count) break;
        }
      } catch(e) {
        console.error('discover error:', e);
        break;
      }
    }

    return repos;
  }

  // ===== 2. 获取 README =====
  async function fetchReadme(fullName) {
    var keys = getKeys();
    var headers = {
      'Accept': 'application/vnd.github.v3.raw',
      'User-Agent': 'GitCast/1.0'
    };
    if (keys.githubToken) {
      headers['Authorization'] = 'token ' + keys.githubToken;
    }

    try {
      var resp = await http({
        url: DEFAULTS.githubApiBase + '/repos/' + fullName + '/readme',
        headers: headers
      });
      if (resp.ok && resp.text) {
        return resp.text.substring(0, 3000);
      }
    } catch(e) {}
    return '';
  }

  // ===== 3. 生成文章（调用 LLM） =====
  async function generateArticle(repo, onProgress) {
    var keys = getKeys();
    if (!keys.llmApiKey) throw new Error('未配置 LLM API Key');

    if (onProgress) onProgress('正在获取 ' + repo.full_name + ' 的 README...');

    var readme = await fetchReadme(repo.full_name);
    var readmeSection = '';
    if (readme) {
      readmeSection = '\n--- 项目 README（节选）---\n' + readme + '\n--- README 节选结束 ---\n';
    }

    var prompt = '请为以下 GitHub 开源项目写一篇详细、有深度的科普文章，面向对技术感兴趣但非专业开发者的读者。\n\n' +
      '项目: ' + repo.full_name + '\n' +
      '描述: ' + (repo.description || '暂无') + '\n' +
      '今日新增星数: ' + repo.stars_today + '\n' +
      readmeSection + '\n' +
      '写作要求：\n' +
      '1. 第一行是标题（不要加#号），标题要有吸引力，体现项目的核心价值\n' +
      '2. 正文 800-1200 字，分成以下几个部分（用空行分隔，不要加小标题前缀符号）：\n\n' +
      '   【开篇引子】用一个生活中的比喻或场景引入，让读者立刻明白这个项目解决什么问题\n' +
      '   【项目是什么】详细解释项目的核心功能和定位，不是简单复述描述，而是深入解读\n' +
      '   【技术原理】用通俗的比喻解释核心技术原理，让非技术人员也能理解它怎么工作的\n' +
      '   【核心功能】列举 2-3 个最有价值的功能，每个功能用 1-2 段详细说明\n' +
      '   【适合谁用】说明目标用户群体和具体使用场景\n' +
      '   【上手难度】评估学习成本，给出快速上手的建议\n' +
      '   【总结展望】这个项目为什么值得关注，未来可能的发展方向\n\n' +
      '3. 语言风格：像跟朋友聊天一样，生动有趣但信息密度高\n' +
      '4. 每个观点都要有具体例子或比喻支撑，不要空话\n' +
      '5. 适当使用类比、对比来帮助理解抽象概念\n';

    if (onProgress) onProgress('正在用 AI 生成文章...');

    var resp = await http({
      url: keys.llmApiBase + '/chat/completions',
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + keys.llmApiKey },
      json: {
        model: keys.llmModel,
        messages: [
          {
            role: 'system',
            content: '你是资深科技博主和技术布道者，擅长用生动通俗的语言深入解读开源项目。你的文章信息密度高、有深度、能让读者真正学到知识。你善于用比喻和类比解释复杂技术，让非技术人员也能理解。每篇文章都要让读者觉得"原来如此，我理解了"。'
          },
          { role: 'user', content: prompt }
        ],
        max_tokens: 3000,
        temperature: 0.8
      }
    });

    if (!resp.ok) throw new Error('LLM API 错误: ' + resp.status + ' ' + (resp.text || '').substring(0, 200));
    if (!resp.json || !resp.json.choices || !resp.json.choices[0]) throw new Error('LLM 返回格式异常');

    var content = resp.json.choices[0].message.content;
    var lines = content.trim().split('\n');
    var title = lines[0].replace(/^#+\s*/, '').trim();
    var body = lines.slice(1).join('\n').trim();

    return {
      title: title,
      project_name: repo.full_name,
      project_url: repo.repo_url,
      stars_today: repo.stars_today,
      body: body,
      word_count: content.length,
      model: keys.llmModel
    };
  }

  // ===== 4. 清理文本用于 TTS =====
  function cleanTextForSpeech(text) {
    // 移除代码块
    text = text.replace(/```[\s\S]*?```/g, '（代码示例省略）');
    // 移除行内代码
    text = text.replace(/`([^`]+)`/g, '$1');
    // 移除标题符号
    text = text.replace(/^#{1,6}\s*/gm, '');
    // 移除粗体/斜体
    text = text.replace(/\*{1,3}([^*]+)\*{1,3}/g, '$1');
    // 移除列表标记
    text = text.replace(/^[\s]*[-*+]\s+/gm, '');
    text = text.replace(/^[\s]*\d+\.\s+/gm, '');
    // 移除链接
    text = text.replace(/\[([^\]]+)\]\([^\)]+\)/g, '$1');
    // 移除引用标记
    text = text.replace(/^>\s*/gm, '');
    // 移除分隔线
    text = text.replace(/^[-=]{3,}$/gm, '');
    // 移除表格符号
    text = text.replace(/\|/g, ' ');
    // 压缩空行
    text = text.replace(/\n{3,}/g, '\n\n');
    // 清理首尾空格
    text = text.replace(/^[ \t]+/gm, '').replace(/[ \t]+$/gm, '');
    text = text.replace(/【/g, '').replace(/】/g, '。');
    text = text.replace(/---/g, '');
    return text.trim();
  }

  // ===== 5. 生成 TTS 音频 =====
  async function generateTTS(text, voice, speed) {
    var keys = getKeys();
    if (!keys.llmApiKey) throw new Error('未配置 LLM API Key');

    var voiceKey = VOICES[voice] ? voice : 'alex';
    var voiceId = VOICES[voiceKey].id;
    var cleanText = cleanTextForSpeech(text);
    var textToSend = cleanText.substring(0, 50000);

    var resp = await http({
      url: keys.llmApiBase + '/audio/speech',
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + keys.llmApiKey },
      json: {
        model: DEFAULTS.ttsModel,
        input: textToSend,
        voice: voiceId,
        response_format: 'mp3',
        speed: speed || 1.0
      },
      responseType: 'blob'
    });

    if (!resp.ok) throw new Error('TTS API 错误: ' + resp.status);
    if (!resp.data) throw new Error('TTS 返回为空');

    // 返回 Blob
    return new Blob([resp.data], { type: 'audio/mpeg' });
  }

  // ===== 6. 完整生成流程（替代 quickgen） =====
  async function runGeneration(language, count, onProgress) {
    var startTime = Date.now();
    var articles = [];

    // 1. 发现项目
    if (onProgress) onProgress({ phase: 'discover', message: '正在发现 GitHub 项目...' });
    var repos = await discoverRepos(language, count, function(msg) {
      if (onProgress) onProgress({ phase: 'discover', message: msg });
    });

    if (!repos || repos.length === 0) {
      return { articles: [], total: 0, duration_sec: 0 };
    }

    var targets = repos.slice(0, count);

    // 2. 逐个生成文章（并发控制）
    var concurrency = 3;
    var index = 0;

    async function genNext() {
      while (index < targets.length) {
        var i = index++;
        var repo = targets[i];
        if (onProgress) onProgress({
          phase: 'generating',
          message: '正在生成第 ' + (i + 1) + '/' + targets.length + ' 篇：' + repo.full_name,
          current: i + 1,
          total: targets.length,
          project: repo.full_name
        });

        try {
          var article = await generateArticle(repo);
          articles.push(article);
        } catch(e) {
          console.error('生成失败 ' + repo.full_name + ':', e);
          if (onProgress) onProgress({
            phase: 'error',
            message: '项目 ' + repo.full_name + ' 生成失败: ' + e.message
          });
        }
      }
    }

    // 启动并发
    var workers = [];
    for (var w = 0; w < concurrency; w++) workers.push(genNext());
    await Promise.all(workers);

    var duration = Math.round((Date.now() - startTime) / 1000);

    if (onProgress) onProgress({
      phase: 'done',
      message: '完成！共生成 ' + articles.length + ' 篇文章，耗时 ' + duration + ' 秒'
    });

    return { articles: articles, total: articles.length, duration_sec: duration };
  }

  // ===== 导出 =====
  global.GitCastEngine = {
    VOICES: VOICES,
    DEFAULTS: DEFAULTS,
    getKeys: getKeys,
    saveKeys: saveKeys,
    hasKeys: hasKeys,
    discoverRepos: discoverRepos,
    generateArticle: generateArticle,
    generateTTS: generateTTS,
    cleanTextForSpeech: cleanTextForSpeech,
    runGeneration: runGeneration,
    http: http,
    isStandalone: function() {
      return window.matchMedia('(display-mode: standalone)').matches ||
             window.navigator.standalone === true ||
             isCapacitor;
    }
  };

})(typeof window !== 'undefined' ? window : this);
