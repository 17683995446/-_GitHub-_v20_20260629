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

  // ===== 2b. 获取仓库文件树 =====
  async function fetchFileTree(fullName) {
    var keys = getKeys();
    var headers = {
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'GitCast/1.0'
    };
    if (keys.githubToken) {
      headers['Authorization'] = 'token ' + keys.githubToken;
    }

    try {
      var resp = await http({
        url: DEFAULTS.githubApiBase + '/repos/' + fullName + '/git/trees/HEAD?recursive=1',
        headers: headers
      });
      if (resp.ok && resp.json && resp.json.tree) {
        return resp.json.tree;
      }
    } catch(e) {}
    return [];
  }

  // ===== 2c. 从文件树中智能识别核心源文件 =====
  function identifyCoreFiles(tree) {
    // 核心文件名模式（权重越高越重要）
    var CORE_PATTERNS = [
      { regex: /\b(core|engine|kernel|runtime|scheduler|executor|pipeline)\b/i, weight: 10 },
      { regex: /\b(main|app|index|server|handler|router|controller)\b/i, weight: 8 },
      { regex: /\b(model|schema|types|interface|protocol)\b/i, weight: 7 },
      { regex: /\b(allocator|gc|memory|buffer|pool|cache)\b/i, weight: 9 },
      { regex: /\b(parser|lexer|compiler|optimizer|transformer)\b/i, weight: 9 },
      { regex: /\b(worker|task|job|queue|channel|concurrent)\b/i, weight: 8 },
      { regex: /\b(crypto|auth|tls|ssl|encrypt|secure)\b/i, weight: 8 },
      { regex: /\b(store|db|database|storage|repository|dao)\b/i, weight: 7 },
      { regex: /\b(config|setting|option|feature)\b/i, weight: 5 },
      { regex: /\b(util|helper|common|base)\b/i, weight: 4 },
    ];

    // 排除的文件（不感兴趣）
    var EXCLUDE = /\.(md|txt|json|ya?ml|toml|ini|env|lock|sum|mod|gitignore|dockerfile|makefile|license|changelog|contributing)$/i;
    var EXCLUDE_DIR = /node_modules|vendor|third_party|dist|build|target|\.git|test|spec|docs|example|demo/i;

    var candidates = [];
    for (var i = 0; i < tree.length; i++) {
      var entry = tree[i];
      if (entry.type !== 'blob') continue;
      var path = entry.path;

      // 排除目录
      if (EXCLUDE_DIR.test(path)) continue;
      // 排除非代码文件
      if (EXCLUDE.test(path)) continue;
      // 只看源代码文件
      if (!/\.(py|go|rs|ts|js|java|kt|c|cc|cpp|h|hpp|rb|swift|zig|nim|dart|lua|sh|scala|clj|ex|exs|hs|ml|fs|cr|d|jl|php)\b/i.test(path)) continue;

      // 计算权重
      var basename = path.split('/').pop().replace(/\.\w+$/, '');
      var weight = 0;
      for (var p = 0; p < CORE_PATTERNS.length; p++) {
        if (CORE_PATTERNS[p].regex.test(basename)) {
          weight = Math.max(weight, CORE_PATTERNS[p].weight);
        }
      }
      // 路径深度加分（根目录或 src/ 下的文件更重要）
      var depth = (path.match(/\//g) || []).length;
      if (depth === 0) weight += 3; // 根目录文件
      else if (depth === 1) weight += 2; // src/ 下一级
      // 文件大小适中加分（太小可能是空文件，太大可能太杂）
      var size = entry.size || 0;
      if (size > 500 && size < 30000) weight += 2;

      if (weight > 0) {
        candidates.push({ path: path, weight: weight, size: size });
      }
    }

    // 按权重排序，取前 5 个
    candidates.sort(function(a, b) { return b.weight - a.weight; });
    return candidates.slice(0, 5);
  }

  // ===== 2d. 获取单个文件内容 =====
  async function fetchFileContent(fullName, filePath) {
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
        url: DEFAULTS.githubApiBase + '/repos/' + fullName + '/contents/' + encodeURIComponent(filePath),
        headers: headers
      });
      if (resp.ok && resp.text) {
        return resp.text.substring(0, 2500);
      }
    } catch(e) {}
    return '';
  }

  // ===== 2e. 获取项目仓库元信息（stars, forks, languages, topics） =====
  async function fetchRepoMeta(fullName) {
    var keys = getKeys();
    var headers = {
      'Accept': 'application/vnd.github.v3+json',
      'User-Agent': 'GitCast/1.0'
    };
    if (keys.githubToken) {
      headers['Authorization'] = 'token ' + keys.githubToken;
    }

    try {
      var resp = await http({
        url: DEFAULTS.githubApiBase + '/repos/' + fullName,
        headers: headers
      });
      if (resp.ok && resp.json) {
        var d = resp.json;
        return {
          stars: d.stargazers_count || 0,
          forks: d.forks_count || 0,
          watchers: d.subscribers_count || 0,
          open_issues: d.open_issues_count || 0,
          language: d.language || '',
          topics: d.topics || [],
          license: (d.license && d.license.name) || 'Unknown',
          created_at: d.created_at || '',
          pushed_at: d.pushed_at || '',
          size: d.size || 0,
          default_branch: d.default_branch || 'main',
          description: d.description || ''
        };
      }
    } catch(e) {}
    return null;
  }

  // ===== 3. 生成两人对话式播客文章（调用 LLM） =====
  async function generateArticle(repo, onProgress) {
    var keys = getKeys();
    if (!keys.llmApiKey) throw new Error('未配置 LLM API Key');

    // === 并行获取：README + 仓库元信息 + 文件树 ===
    if (onProgress) onProgress('正在分析 ' + repo.full_name + ' 的项目结构...');

    var results = await Promise.allSettled([
      fetchReadme(repo.full_name),
      fetchRepoMeta(repo.full_name),
      fetchFileTree(repo.full_name)
    ]);

    var readme = results[0].status === 'fulfilled' ? results[0].value : '';
    var meta = results[1].status === 'fulfilled' ? results[1].value : null;
    var fileTree = results[2].status === 'fulfilled' ? results[2].value : [];

    // === 从文件树中智能识别核心源文件 ===
    var coreFiles = identifyCoreFiles(fileTree);

    // === 并行获取核心文件代码内容 ===
    var codeSnippets = [];
    if (coreFiles.length > 0) {
      if (onProgress) onProgress('正在读取核心源代码（' + coreFiles.length + ' 个文件）...');

      var fileResults = await Promise.allSettled(
        coreFiles.map(function(f) { return fetchFileContent(repo.full_name, f.path); })
      );

      for (var i = 0; i < fileResults.length; i++) {
        if (fileResults[i].status === 'fulfilled' && fileResults[i].value) {
          codeSnippets.push({
            path: coreFiles[i].path,
            content: fileResults[i].value
          });
        }
      }
    }

    // === 构建上下文信息 ===
    var contextParts = [];

    // 元信息
    if (meta) {
      contextParts.push('--- 仓库元信息 ---');
      contextParts.push('Stars: ' + meta.stars + ' | Forks: ' + meta.forks + ' | Watchers: ' + meta.watchers);
      contextParts.push('语言: ' + meta.language + ' | License: ' + meta.license);
      contextParts.push('Topics: ' + (meta.topics.length > 0 ? meta.topics.join(', ') : '无'));
      contextParts.push('仓库大小: ' + meta.size + ' KB');
      contextParts.push('');
    }

    // README
    if (readme) {
      contextParts.push('--- README（节选）---');
      contextParts.push(readme);
      contextParts.push('');
    }

    // 文件结构概览（前 40 个源文件路径）
    if (fileTree.length > 0) {
      var codePaths = fileTree
        .filter(function(e) { return e.type === 'blob' && /\.(py|go|rs|ts|js|java|kt|c|cc|cpp|h|hpp|rb|swift|zig|nim)\b/i.test(e.path); })
        .map(function(e) { return e.path; })
        .slice(0, 40);
      if (codePaths.length > 0) {
        contextParts.push('--- 项目文件结构（源代码文件列表）---');
        contextParts.push(codePaths.join('\n'));
        contextParts.push('');
      }
    }

    // 核心代码片段
    if (codeSnippets.length > 0) {
      contextParts.push('--- 核心源代码（智能选取的 ' + codeSnippets.length + ' 个关键文件）---');
      for (var s = 0; s < codeSnippets.length; s++) {
        contextParts.push('【文件: ' + codeSnippets[s].path + '】');
        contextParts.push(codeSnippets[s].content);
        contextParts.push('');
      }
      contextParts.push('--- 核心源代码结束 ---');
      contextParts.push('');
    }

    var context = contextParts.join('\n');

    var prompt = '请为以下 GitHub 开源项目创作一期两人对话式技术播客脚本。\n\n' +
      '项目: ' + repo.full_name + '\n' +
      '描述: ' + (repo.description || '暂无') + '\n\n' +
      context + '\n' +
      '播客形式：两位主持人对话，角色设定：\n' +
      '  - 阿明（技术达人，资深开发者，对项目了如指掌，负责深入解读技术细节）\n' +
      '  - 小白（科技爱好者，非专业开发者，代表听众提问，追问"为什么"和"怎么做到的"）\n\n' +
      '输出格式（严格遵守）：\n' +
      '1. 第一行是标题（不要加#号），标题要有吸引力，像播客节目名\n' +
      '2. 从第二行开始是对话内容，格式为：\n' +
      '   阿明：对话内容...\n' +
      '   小白：对话内容...\n' +
      '   阿明：对话内容...\n' +
      '   （以此类推，每句对话单独一行，角色名后跟冒号）\n\n' +
      '对话内容要求（极其重要）：\n' +
      '  - 对话轮次：15-25 轮（30-50 句对话），总字数 2500-3500 字\n' +
      '  - 开篇：小白用生活场景引入（"我最近遇到一个问题..."），阿明自然引出项目\n\n' +
      '  - 技术深度（必须基于上面提供的源代码和文件结构来分析，不能空谈）：\n' +
      '    * 阿明要讲清楚具体的技术实现细节，必须引用代码中的关键逻辑\n' +
      '    * 分析核心文件中用到的架构模式（如工厂模式、观察者、事件驱动等）\n' +
      '    * 解释关键算法/数据结构的工作原理（如"它用了一个 LRU 缓存，这意味着..."）\n' +
      '    * 对比同类方案的优劣（如"和 X 相比，它用了 Y 方法，好处是 Z"）\n' +
      '    * 指出代码中的巧妙设计（如"你看这个 xxx 函数，它先做了 A 再做 B，这样避免了 C 问题"）\n' +
      '    * 如果代码中有性能优化手段（如池化、零拷贝、延迟加载等），必须讲出来\n' +
      '    * 基于代码推断项目的核心创新点（"这个项目最大的创新在于..."）\n\n' +
      '  - 通俗易懂：\n' +
      '    * 小白在关键处追问"这个具体怎么理解的？""能给个比喻吗？"\n' +
      '    * 阿明用生活中的比喻解释抽象概念（如"这就像快递分拣中心..."）\n' +
      '    * 技术术语第一次出现时，阿明会用一句话解释\n' +
      '    * 提到代码时不要念代码，而是用大白话描述代码做了什么\n\n' +
      '  - 节奏感：\n' +
      '    * 小白适时表达惊讶或恍然大悟（"原来如此！""这个设计真巧妙"）\n' +
      '    * 阿明偶尔抛出趣味冷知识或行业八卦\n' +
      '    * 不要机械问答，要有自然的对话感\n' +
      '  - 结尾：小白总结收获，阿明给出上手建议和学习路径\n\n' +
      '关键提醒：不要出现任何旁白、解说词、小标题，整篇内容只有"阿明：..."和"小白：..."交替的对话。\n' +
      '你必须真正阅读和理解上面提供的源代码，对话中要体现对代码的理解，不能泛泛而谈。';

    if (onProgress) onProgress('正在用 AI 生成对话式播客...');

    var resp = await http({
      url: keys.llmApiBase + '/chat/completions',
      method: 'POST',
      headers: { 'Authorization': 'Bearer ' + keys.llmApiKey },
      json: {
        model: keys.llmModel,
        messages: [
          {
            role: 'system',
            content: '你是一位资深技术播客制作人兼全栈工程师，擅长创作两人对话式技术节目。你会仔细阅读项目源代码，从中提取核心技术细节和创新点，用通俗易懂的对话形式讲出来。你的脚本信息密度极高，每句话都有价值，听众听完后能真正理解项目的技术精髓和代码之美。你绝不写空话套话。'
          },
          { role: 'user', content: prompt }
        ],
        max_tokens: 5000,
        temperature: 0.85
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
      model: keys.llmModel,
      is_dialogue: true
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

  // ===== 5b. 对话式 TTS：解析对话，双声音交替合成 =====
  // 对话格式："阿明：xxx" / "小白：yyy"，阿明用低沉男声，小白用温柔女声
  function parseDialogue(text) {
    var lines = text.split('\n');
    var segments = [];
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i].trim();
      if (!line) continue;
      // 匹配 "角色名：内容" 或 "角色名: 内容"
      var match = line.match(/^(阿明|小白)\s*[：:]\s*(.+)$/);
      if (match) {
        segments.push({ speaker: match[1], text: match[2] });
      } else {
        // 不匹配的行：如果上一段存在，追加到上一段；否则作为旁白
        if (segments.length > 0) {
          segments[segments.length - 1].text += ' ' + line;
        } else {
          segments.push({ speaker: '阿明', text: line });
        }
      }
    }
    return segments;
  }

  async function generateDialogueTTS(text, voice, speed) {
    var keys = getKeys();
    if (!keys.llmApiKey) throw new Error('未配置 LLM API Key');

    var segments = parseDialogue(text);
    if (segments.length === 0) {
      // 解析不到对话格式，回退普通 TTS
      return generateTTS(text, voice, speed);
    }

    // 阿明用男声（alex），小白用女声（claire）
    var hostVoice = VOICES[voice] ? voice : 'alex';
    var guestVoice = 'claire';
    // 如果用户选的就是女声，阿明用 david，小白用用户选的
    if (VOICES[voice] && VOICES[voice].name.indexOf('女') >= 0) {
      hostVoice = 'david';
      guestVoice = voice;
    }

    var hostVoiceId = VOICES[hostVoice].id;
    var guestVoiceId = VOICES[guestVoice].id;

    // 逐段合成，收集 Blob
    var audioBlobs = [];
    for (var i = 0; i < segments.length; i++) {
      var seg = segments[i];
      var segVoiceId = seg.speaker === '阿明' ? hostVoiceId : guestVoiceId;
      var segText = cleanTextForSpeech(seg.text);
      if (!segText) continue;

      try {
        var resp = await http({
          url: keys.llmApiBase + '/audio/speech',
          method: 'POST',
          headers: { 'Authorization': 'Bearer ' + keys.llmApiKey },
          json: {
            model: DEFAULTS.ttsModel,
            input: segText.substring(0, 5000),
            voice: segVoiceId,
            response_format: 'mp3',
            speed: speed || 1.0
          },
          responseType: 'blob'
        });

        if (resp.ok && resp.data) {
          audioBlobs.push(new Blob([resp.data], { type: 'audio/mpeg' }));
        }
      } catch(e) {
        console.warn('dialogue TTS segment ' + i + ' failed:', e);
      }
    }

    if (audioBlobs.length === 0) throw new Error('对话 TTS 全部段失败');

    // 拼接所有音频 Blob
    return new Blob(audioBlobs, { type: 'audio/mpeg' });
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
    generateDialogueTTS: generateDialogueTTS,
    parseDialogue: parseDialogue,
    fetchFileTree: fetchFileTree,
    identifyCoreFiles: identifyCoreFiles,
    fetchFileContent: fetchFileContent,
    fetchRepoMeta: fetchRepoMeta,
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
