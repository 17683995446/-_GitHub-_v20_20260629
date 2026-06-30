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
      { regex: /\b(allocator|gc|memory|buffer|pool|cache)\b/i, weight: 9 },
      { regex: /\b(parser|lexer|compiler|optimizer|transformer)\b/i, weight: 9 },
      { regex: /\b(main|app|index|server|handler|router|controller)\b/i, weight: 8 },
      { regex: /\b(worker|task|job|queue|channel|concurrent)\b/i, weight: 8 },
      { regex: /\b(crypto|auth|tls|ssl|encrypt|secure)\b/i, weight: 8 },
      { regex: /\b(model|schema|types|interface|protocol)\b/i, weight: 7 },
      { regex: /\b(store|db|database|storage|repository|dao)\b/i, weight: 7 },
      { regex: /\b(client|adapter|provider|factory|builder)\b/i, weight: 7 },
      { regex: /\b(config|setting|option|feature)\b/i, weight: 5 },
      { regex: /\b(util|helper|common|base)\b/i, weight: 4 },
    ];

    // 排除的文件（不感兴趣）
    var EXCLUDE = /\.(md|txt|lock|sum|gitignore|license|changelog|contributing)$/i;
    var EXCLUDE_DIR = /node_modules|vendor|third_party|dist|build|target|\.git|spec|docs|example|demo/i;

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
      if (size > 500 && size < 50000) weight += 2;

      if (weight > 0) {
        candidates.push({ path: path, weight: weight, size: size });
      }
    }

    // 按权重排序，取前 8 个
    candidates.sort(function(a, b) { return b.weight - a.weight; });
    return candidates.slice(0, 8);
  }

  // ===== 2c-2. 智能截取文件内容（优先保留类定义、函数签名、关键逻辑） =====
  function smartExtractCode(rawContent, maxLen) {
    var content = rawContent;
    var limit = maxLen || 3500;

    // 如果文件不长，直接返回
    if (content.length <= limit) return content;

    var lines = content.split('\n');
    var result = [];
    var currentLen = 0;

    // 第一优先级：类定义、struct/trait/impl 定义
    var priorityPatterns = [
      /^\s*(public\s+|private\s+|protected\s+)?(class|struct|trait|impl|interface|enum|union|module)\s+/i,
      /^\s*(async\s+)?(pub\s+|public\s+|private\s+)?(fn|func|function|def|sub|method)\s+/i,
      /^\s*export\s+(default\s+)?(class|function|const|let|var|interface|type|enum)\s+/i,
    ];

    function isPriority(line) {
      for (var i = 0; i < priorityPatterns.length; i++) {
        if (priorityPatterns[i].test(line)) return true;
      }
      return false;
    }

    // 先提取所有优先级行及其上下文
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      if (isPriority(line)) {
        // 提取该行 + 后面 15 行上下文
        var start = Math.max(0, i - 2);
        var end = Math.min(lines.length, i + 15);
        for (var j = start; j < end; j++) {
          if (result.indexOf(j) === -1 && currentLen < limit * 0.6) {
            result.push(j);
            currentLen += lines[j].length + 1;
          }
        }
      }
    }

    // 按行号排序，构建输出
    result.sort(function(a, b) { return a - b; });

    var output = [];
    var prevLine = -1;
    for (var k = 0; k < result.length; k++) {
      var lineNum = result[k];
      if (prevLine >= 0 && lineNum > prevLine + 1) {
        output.push('    ... (省略 ' + (lineNum - prevLine - 1) + ' 行) ...');
      }
      output.push(lines[lineNum]);
      prevLine = lineNum;
    }

    var extracted = output.join('\n');

    // 如果优先级内容不够，补充文件开头
    if (extracted.length < limit * 0.5) {
      var remaining = limit - extracted.length;
      var headContent = content.substring(0, remaining);
      extracted = headContent + '\n\n--- (以上为文件开头，以下是关键定义) ---\n\n' + extracted;
    }

    return extracted.substring(0, limit);
  }

  // ===== 2c-3. 获取依赖文件内容 =====
  async function fetchDependencyInfo(fullName, fileTree) {
    var depFiles = [
      'package.json', 'requirements.txt', 'go.mod', 'Cargo.toml',
      'pom.xml', 'build.gradle', 'Gemfile', 'setup.py', 'pyproject.toml',
      'composer.json', 'mix.exs', 'CMakeLists.txt', 'Makefile'
    ];

    // 从文件树中找到存在的依赖文件
    var found = [];
    for (var i = 0; i < fileTree.length; i++) {
      var entry = fileTree[i];
      if (entry.type !== 'blob') continue;
      var basename = entry.path.split('/').pop();
      // 只取根目录或一级目录的依赖文件
      var depth = (entry.path.match(/\//g) || []).length;
      if (depth > 1) continue;
      if (depFiles.indexOf(basename) >= 0) {
        found.push(entry.path);
      }
    }

    if (found.length === 0) return '';

    var keys = getKeys();
    var headers = {
      'Accept': 'application/vnd.github.v3.raw',
      'User-Agent': 'GitCast/1.0'
    };
    if (keys.githubToken) {
      headers['Authorization'] = 'token ' + keys.githubToken;
    }

    var parts = ['--- 依赖与构建配置 ---'];
    for (var f = 0; f < found.length && f < 3; f++) {
      try {
        var resp = await http({
          url: DEFAULTS.githubApiBase + '/repos/' + fullName + '/contents/' + encodeURIComponent(found[f]),
          headers: headers
        });
        if (resp.ok && resp.text) {
          // 对 package.json 只提取 dependencies 部分
          var content = resp.text;
          if (found[f] === 'package.json') {
            try {
              var pkg = JSON.parse(content);
              var deps = pkg.dependencies || {};
              var devDeps = pkg.devDependencies || {};
              var depLines = [];
              for (var k in deps) depLines.push('  ' + k + ': ' + deps[k]);
              if (Object.keys(devDeps).length > 0) {
                depLines.push('  --- devDependencies ---');
                for (var dk in devDeps) depLines.push('  ' + dk + ': ' + devDeps[dk]);
              }
              content = depLines.join('\n');
            } catch(e) {}
          }
          parts.push('【' + found[f] + '】');
          parts.push(content.substring(0, 1500));
          parts.push('');
        }
      } catch(e) {}
    }
    parts.push('--- 依赖配置结束 ---');
    return parts.join('\n');
  }

  // ===== 2d. 获取单个文件内容（智能截取关键部分） =====
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
        // 智能截取：优先保留类定义、函数签名、关键逻辑
        return smartExtractCode(resp.text, 3500);
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

    // === 并行获取核心文件代码内容 + 依赖信息 ===
    var codeSnippets = [];
    var depInfo = '';
    if (coreFiles.length > 0 || fileTree.length > 0) {
      if (onProgress) onProgress('正在读取核心源代码（' + coreFiles.length + ' 个文件）+ 依赖分析...');

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

      // 获取依赖文件
      try {
        depInfo = await fetchDependencyInfo(repo.full_name, fileTree);
      } catch(e) {}
    }

    // === 构建上下文信息 ===
    var contextParts = [];

    // 元信息
    if (meta) {
      contextParts.push('=== 仓库元信息 ===');
      contextParts.push('Stars: ' + meta.stars + ' | Forks: ' + meta.forks + ' | Watchers: ' + meta.watchers);
      contextParts.push('语言: ' + meta.language + ' | License: ' + meta.license);
      contextParts.push('Topics: ' + (meta.topics.length > 0 ? meta.topics.join(', ') : '无'));
      contextParts.push('仓库大小: ' + meta.size + ' KB');
      contextParts.push('');
    }

    // 依赖信息
    if (depInfo) {
      contextParts.push(depInfo);
      contextParts.push('');
    }

    // README
    if (readme) {
      contextParts.push('=== README（节选）===');
      contextParts.push(readme);
      contextParts.push('');
    }

    // 文件结构概览（前 60 个源文件路径）
    if (fileTree.length > 0) {
      var codePaths = fileTree
        .filter(function(e) { return e.type === 'blob' && /\.(py|go|rs|ts|js|java|kt|c|cc|cpp|h|hpp|rb|swift|zig|nim)\b/i.test(e.path); })
        .map(function(e) { return e.path; })
        .slice(0, 60);
      if (codePaths.length > 0) {
        contextParts.push('=== 项目文件结构（源代码文件列表）===');
        contextParts.push(codePaths.join('\n'));
        contextParts.push('');
      }
    }

    // 核心代码片段 + AST 结构分析
    if (codeSnippets.length > 0) {
      // 尝试用 tree-sitter 做 AST 分析
      var astSummaries = [];
      var hasAST = false;

      try {
        if (typeof TreeSitterAnalyzer !== 'undefined') {
          await TreeSitterAnalyzer.init();
          if (TreeSitterAnalyzer.isAvailable()) {
            hasAST = true;
            if (onProgress) onProgress('正在进行 AST 代码结构分析...');
            for (var s2 = 0; s2 < codeSnippets.length; s2++) {
              var analysis = await TreeSitterAnalyzer.analyzeCode(
                codeSnippets[s2].path,
                codeSnippets[s2].content
              );
              if (analysis && analysis.summary) {
                astSummaries.push({
                  path: codeSnippets[s2].path,
                  summary: analysis.summary,
                  stats: {
                    classes: analysis.classes.length,
                    functions: analysis.functions.length,
                    interfaces: analysis.interfaces.length,
                    structs: analysis.structs.length,
                    traits: analysis.traits.length
                  }
                });
              }
            }
          }
        }
      } catch(e) {
        console.warn('[engine] AST analysis failed, using raw code:', e.message);
      }

      // 构建 AST 结构地图（如果有）
      if (astSummaries.length > 0) {
        contextParts.push('=== 代码结构 AST 分析（基于 Tree-sitter 真实解析）===');
        for (var a = 0; a < astSummaries.length; a++) {
          var as = astSummaries[a];
          contextParts.push('【文件: ' + as.path + '】');
          contextParts.push(as.summary);
          contextParts.push('');
        }
        contextParts.push('=== AST 结构分析结束 ===');
        contextParts.push('');
      }

      // 保留原始代码片段（截取关键部分）
      contextParts.push('=== 核心源代码（智能选取的 ' + codeSnippets.length + ' 个关键文件）===');
      for (var s = 0; s < codeSnippets.length; s++) {
        contextParts.push('【文件: ' + codeSnippets[s].path + '】');
        contextParts.push(codeSnippets[s].content);
        contextParts.push('');
      }
      contextParts.push('=== 核心源代码结束 ===');
      contextParts.push('');
    }

    var context = contextParts.join('\n');

    var prompt = '请为以下 GitHub 开源项目创作一期两人对话式技术播客脚本。\n\n' +
      '项目: ' + repo.full_name + '\n' +
      '描述: ' + (repo.description || '暂无') + '\n\n' +
      context + '\n' +
      '播客形式：两位主持人对话，角色设定：\n' +
      '  - 阿明（资深全栈工程师，对项目源代码了如指掌，负责深入解读技术细节）\n' +
      '  - 小白（科技爱好者，非专业开发者，代表听众提问，追问"为什么"和"怎么做到的"）\n\n' +
      '输出格式（严格遵守）：\n' +
      '1. 第一行是标题（不要加#号），标题要有吸引力，像播客节目名\n' +
      '2. 从第二行开始是对话内容，格式为：\n' +
      '   阿明：对话内容...\n' +
      '   小白：对话内容...\n' +
      '   （每句对话单独一行，角色名后跟冒号）\n\n' +
      '=== 技术分析框架（阿明必须覆盖以下每个维度）===\n\n' +
      '【维度1：架构分析】\n' +
      '  - 项目的整体架构是什么？（单体/微服务/事件驱动/管道-过滤器等）\n' +
      '  - 核心模块如何划分？从文件结构中看出什么设计？\n' +
      '  - 用了哪些设计模式？（结合代码中的具体类/函数说明）\n' +
      '  - 模块间如何通信？（函数调用/事件总线/消息队列/RPC等）\n\n' +
      '【维度2：核心算法与数据结构】\n' +
      '  - 项目用了哪些关键算法？（必须从代码中找到证据）\n' +
      '  - 用了哪些特殊数据结构？（如 LRU Cache/跳表/布隆过滤器/环形缓冲区等）\n' +
      '  - 这些算法/数据结构为什么选这个而不是其他？有什么 trade-off？\n\n' +
      '【维度3：性能工程】\n' +
      '  - 代码中有哪些性能优化手段？（池化/零拷贝/延迟加载/批处理/缓存策略等）\n' +
      '  - 并发模型是什么？（线程池/协程/异步IO/Actor模型等，结合代码说明）\n' +
      '  - 内存管理有什么特点？（手动管理/GC/引用计数/ Arena 等）\n\n' +
      '【维度4：依赖与技术选型】\n' +
      '  - 从依赖文件看，项目选择了哪些关键库？为什么选这些？\n' +
      '  - 有没有自己造轮子？为什么不直接用现成的？\n' +
      '  - 技术栈选型有什么独到之处？\n\n' +
      '【维度5：核心创新点】\n' +
      '  - 这个项目最大的技术创新是什么？（必须有代码证据支撑）\n' +
      '  - 和同类项目相比，它的技术方案有什么独特优势？\n' +
      '  - 哪些设计让你觉得"这很巧妙"？\n\n' +
      '=== 对话要求 ===\n\n' +
      '  - 对话轮次：20-30 轮（40-60 句对话），总字数 3500-5000 字\n' +
      '  - 开篇：小白用生活场景引入，阿明自然引出项目\n' +
      '  - 技术深度：必须基于上面提供的源代码分析，每句话都要有信息量\n' +
      '    * 阿明要引用具体代码："你看这个 xxx 文件里的 yyy 函数，它先做了 A，然后做了 B"\n' +
      '    * 不要念代码，用大白话描述代码做了什么和为什么这样做\n' +
      '    * 提到设计模式时要解释它在代码中怎么体现的\n' +
      '  - 通俗易懂：\n' +
      '    * 小白在关键处追问"这个具体怎么实现的？""为什么这样做而不那样做？"\n' +
      '    * 阿明用生活比喻解释抽象概念\n' +
      '    * 技术术语第一次出现时用一句话解释\n' +
      '  - 节奏感：小白会惊讶/恍然大悟/质疑追问，阿明会抛冷知识和行业背景\n' +
      '  - 结尾：小白总结技术收获，阿明给出上手建议和学习路径\n\n' +
      '关键提醒：不要出现任何旁白、解说词、小标题。整篇内容只有"阿明：..."和"小白：..."交替的对话。\n' +
      '你必须真正阅读和理解上面提供的源代码和依赖文件，对话中要体现对代码的深度理解，不能泛泛而谈。\n' +
      '上面5个技术维度必须全部覆盖，每个维度至少 3-5 句对话讨论。';

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
            content: '你是一位资深全栈工程师兼技术播客制作人。你会仔细阅读项目源代码和依赖文件，从中提取核心架构设计、算法原理、性能优化手段和创新能力。你的对话脚本信息密度极高，每句话都有技术价值。你善于用生活比喻解释代码逻辑，让非技术人员也能理解"这段代码为什么这样写"。你绝不写空话套话，每句话都指向具体的技术实现。'
          },
          { role: 'user', content: prompt }
        ],
        max_tokens: 6000,
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
    smartExtractCode: smartExtractCode,
    fetchFileContent: fetchFileContent,
    fetchDependencyInfo: fetchDependencyInfo,
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
