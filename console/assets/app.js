(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var accent3 = style.getPropertyValue('--accent3').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // ===== State =====
  var generatedArticles = [];
  var totalStats = { articles: 0, audio: 0, projects: 0, publishes: 0 };

  // 音频播放器状态（提前声明，供 renderRecentPodcasts 初始化时使用）
  var playbackRate = 1.0;
  var selectedVoice = 'alex';
  var speedOptions = [1.0, 1.25, 1.5, 1.75, 2.0];
  var speedLabels = { 1.0: '1.0x', 1.25: '1.25x', 1.5: '1.5x', 1.75: '1.75x', 2.0: '2.0x' };
  var voiceOptions = [
    { key: 'alex', label: '沉稳男声' },
    { key: 'benjamin', label: '低沉男声' },
    { key: 'charles', label: '磁性男声' },
    { key: 'david', label: '欢快男声' },
    { key: 'anna', label: '沉稳女声' },
    { key: 'bella', label: '激情女声' },
    { key: 'claire', label: '温柔女声' },
    { key: 'diana', label: '欢快女声' }
  ];
  // 全局音量（0.0 ~ 3.0），1.0 = 原始音量，3.0 = 放大 3 倍，提前声明避免 NaN
  var audioVolume = 1.5;
  // 从 localStorage 恢复音量（提前执行）
  try {
    var _savedVol = localStorage.getItem('gitcast_volume');
    if (_savedVol !== null) audioVolume = parseFloat(_savedVol);
  } catch(e) {}
  // 连续播放开关
  var continuousPlay = false;
  try {
    var _savedCont = localStorage.getItem('gitcast_continuous');
    if (_savedCont !== null) continuousPlay = _savedCont === 'true';
  } catch(e) {}
  // 当前播放队列及索引
  var playQueue = [];
  var currentQueueIndex = -1;

  // ===== LocalStorage 持久化 =====
  var STORAGE_KEY = 'gitcast_articles_v1';
  var STATS_KEY = 'gitcast_stats_v1';

  function saveToStorage() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(generatedArticles));
      localStorage.setItem(STATS_KEY, JSON.stringify(totalStats));
    } catch(e) {
      console.warn('localStorage 保存失败（可能已满）:', e);
    }
  }

  function loadFromStorage() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        generatedArticles = JSON.parse(raw) || [];
      }
      var rawStats = localStorage.getItem(STATS_KEY);
      if (rawStats) {
        totalStats = JSON.parse(rawStats) || totalStats;
      }
    } catch(e) {
      console.warn('localStorage 读取失败:', e);
    }
  }

  window.clearHistory = function() {
    if (!confirm('确定要清除所有历史播客记录吗？此操作不可撤销。')) return;
    generatedArticles = [];
    totalStats = { articles: 0, audio: 0, projects: 0, publishes: 0 };
    localStorage.removeItem(STORAGE_KEY);
    localStorage.removeItem(STATS_KEY);
    updateStats();
    renderRecentPodcasts();
    renderArticlesPage();
    showToast('历史记录已清除', 'success');
  };

  // ===== Utility: Escape HTML to prevent XSS =====
  function escapeHtml(str) {
    if (str == null) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  // ===== Init stat numbers =====
  function updateStats() {
    document.getElementById('stat-articles').textContent = totalStats.articles;
    document.getElementById('stat-audio').textContent = totalStats.audio;
    document.getElementById('stat-projects').textContent = totalStats.projects;
    document.getElementById('stat-publish').textContent = totalStats.publishes;
  }
  // ===== Init: 从 localStorage 恢复历史数据 =====
  loadFromStorage();
  updateStats();
  renderRecentPodcasts();

  // 页面加载后，静默预加载已有文章的音频（不显示"合成中"状态）
  setTimeout(function() {
    if (generatedArticles.length > 0) {
      console.log('[GitCast] 检测到 ' + generatedArticles.length + ' 篇历史文章，静默预加载音频...');
      var recentCount = Math.min(generatedArticles.length, 3);
      for (var i = 0; i < recentCount; i++) {
        setTimeout(function(idx) {
          var textId = 'recent-' + idx;
          var textEl = document.getElementById(textId);
          if (textEl) {
            var text = textEl.textContent || textEl.innerText;
            preGenerateAudio(textId, text, selectedVoice, playbackRate, true);
          }
        }(i), i * 3000);
      }
    }
  }, 3000);

  // ===== Chart: Trend =====
  var trendChart = echarts.init(document.getElementById('chart-trend'), null, { renderer: 'svg' });
  trendChart.setOption({
    animation: false,
    tooltip: { trigger: 'axis', backgroundColor: bg2, borderColor: rule, textStyle: { color: ink }, appendToBody: true },
    grid: { left: 40, right: 20, top: 20, bottom: 30 },
    xAxis: {
      type: 'category',
      data: ['6/23', '6/24', '6/25', '6/26', '6/27', '6/28', '6/29'],
      axisLine: { lineStyle: { color: rule } },
      axisLabel: { color: muted, fontSize: 11 }
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisLabel: { color: muted, fontSize: 11 },
      splitLine: { lineStyle: { color: rule, type: 'dashed' } }
    },
    series: [{
      type: 'line',
      data: [3, 7, 5, 12, 8, 6, 5],
      smooth: true,
      symbol: 'circle',
      symbolSize: 8,
      lineStyle: { color: accent, width: 3 },
      itemStyle: { color: accent },
      areaStyle: {
        color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: accent + '40' },
            { offset: 1, color: accent + '05' }
          ]
        }
      }
    }]
  });

  // ===== Chart: Language Distribution =====
  var langChart = echarts.init(document.getElementById('chart-lang'), null, { renderer: 'svg' });
  langChart.setOption({
    animation: false,
    tooltip: { trigger: 'item', backgroundColor: bg2, borderColor: rule, textStyle: { color: ink }, appendToBody: true },
    legend: {
      bottom: 0,
      textStyle: { color: muted, fontSize: 11 },
      itemWidth: 10, itemHeight: 10
    },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['50%', '45%'],
      label: { color: ink, fontSize: 12 },
      labelLine: { lineStyle: { color: rule } },
      data: [
        { value: 18, name: 'Python', itemStyle: { color: accent } },
        { value: 12, name: 'TypeScript', itemStyle: { color: accent2 } },
        { value: 10, name: 'Rust', itemStyle: { color: accent3 } },
        { value: 8, name: 'Go', itemStyle: { color: '#f0883e' } },
        { value: 8, name: '其他', itemStyle: { color: muted } }
      ]
    }]
  });

  window.addEventListener('resize', function() {
    trendChart.resize();
    langChart.resize();
  });

  // ===== Page Navigation =====
  // Bug fix #4: Use el parameter instead of fragile event global.
  // Handles both nav-item clicks and button clicks (e.g. overview "立即生成").
  window.showPage = function(pageName, el) {
    document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
    document.getElementById('page-' + pageName).classList.add('active');
    document.querySelectorAll('.nav-item').forEach(function(n) { n.classList.remove('active'); });

    if (el && el.classList && el.classList.contains('nav-item')) {
      el.classList.add('active');
    } else {
      // Caller is not a nav-item (e.g. a button); find the matching nav item.
      document.querySelectorAll('.nav-item').forEach(function(n) {
        var onclickAttr = n.getAttribute('onclick') || '';
        if (onclickAttr.indexOf("'" + pageName + "'") !== -1) {
          n.classList.add('active');
        }
      });
    }

    // Bug fix #6: Resize charts when returning to overview (they may have
    // been initialized while hidden, giving them zero dimensions).
    if (pageName === 'overview') {
      setTimeout(function() {
        trendChart.resize();
        langChart.resize();
      }, 50);
      renderRecentPodcasts();
    }

    // Bug fix #5: Render articles page when switching to it.
    if (pageName === 'articles') {
      renderArticlesPage();
      // 渲染后自动预生成音频
      setTimeout(function() {
        preGenerateAudioForArticlesPage();
      }, 500);
    }
  };

  // ===== Chip Selection (single-select) =====
  // Bug fix #3: Changed from multi-select to single-select because the
  // quickgen API accepts one language at a time.
  document.querySelectorAll('#langChips .chip').forEach(function(chip) {
    chip.addEventListener('click', function() {
      document.querySelectorAll('#langChips .chip').forEach(function(c) {
        c.classList.remove('selected');
      });
      chip.classList.add('selected');
    });
  });

  // ===== Toggle Group =====
  document.querySelectorAll('#maxResultsGroup .toggle-item').forEach(function(item) {
    item.addEventListener('click', function() {
      document.querySelectorAll('#maxResultsGroup .toggle-item').forEach(function(i) {
        i.classList.remove('active');
      });
      item.classList.add('active');
    });
  });

  // ===== Concurrency Toggle Group =====
  document.querySelectorAll('#concurrencyGroup .toggle-item').forEach(function(item) {
    item.addEventListener('click', function() {
      document.querySelectorAll('#concurrencyGroup .toggle-item').forEach(function(i) {
        i.classList.remove('active');
      });
      item.classList.add('active');
    });
  });

  // ===== Toast =====
  function showToast(msg, type) {
    var toast = document.getElementById('toast');
    var icon = document.getElementById('toastIcon');
    toast.className = 'toast show ' + (type || '');
    icon.textContent = type === 'success' ? '\u2705' : type === 'error' ? '\u274C' : '\u2139\uFE0F';
    document.getElementById('toastMsg').textContent = msg;
    setTimeout(function() { toast.classList.remove('show'); }, 4000);
  }
  window.showToast = showToast;

  // ===== Trigger Pipeline (异步任务模式) =====
  // 提交任务后立即返回 job_id，前端轮询状态，避免网关 504 超时。
  window.triggerPipeline = function() {
    var selectedChip = document.querySelector('#langChips .chip.selected');
    if (!selectedChip) {
      showToast('请选择一个编程语言', 'error');
      return;
    }

    var lang = selectedChip.dataset.lang;
    var apiLang = lang === 'all' ? '' : lang;

    var maxResults = 5;
    document.querySelectorAll('#maxResultsGroup .toggle-item').forEach(function(i) {
      if (i.classList.contains('active')) maxResults = parseInt(i.dataset.value);
    });

    var concurrency = 5;
    document.querySelectorAll('#concurrencyGroup .toggle-item').forEach(function(i) {
      if (i.classList.contains('active')) concurrency = parseInt(i.dataset.value);
    });

    showToast('正在提交生成任务...', 'info');

    var btn = document.getElementById('btnGenerate');
    if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; btn.textContent = '提交中...'; }

    // 显示任务状态区域
    var result = document.getElementById('jobResult');
    var badge = document.getElementById('jobBadge');
    var idText = document.getElementById('jobIdText');
    var details = document.getElementById('jobDetails');
    result.classList.add('show');
    badge.className = 'job-status-badge running';
    badge.textContent = '运行中';
    idText.textContent = '正在提交任务...';
    details.innerHTML = '<span style="color:var(--accent2);">⏳ 正在发现 GitHub 热门项目...</span>';

    // 1. 提交任务
    fetch('/api/v1/quickgen/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        language: apiLang,
        max_results: maxResults,
        concurrency: concurrency
      })
    })
    .then(function(resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    })
    .then(function(data) {
      if (!data.job_id) throw new Error('未返回任务ID');
      idText.textContent = '任务 ID: ' + data.job_id;
      if (btn) { btn.textContent = '生成中...'; }
      // 2. 轮询状态
      pollJobStatus(data.job_id, lang, maxResults);
    })
    .catch(function(err) {
      if (btn) { btn.disabled = false; btn.style.opacity = '1'; btn.innerHTML = '\u26A1\uFE0F 开始生成'; }
      badge.className = 'job-status-badge failed';
      badge.textContent = '提交失败';
      details.innerHTML = '<span style="color:var(--danger);">❌ ' + escapeHtml(err.message) + '</span>';
      showToast('提交失败: ' + err.message, 'error');
    });
  };

  // ===== 轮询任务状态 =====
  var pollTimer = null;
  var lastCompletedCount = 0;
  var partialAudioStarted = {};
  function pollJobStatus(jobId, lang, maxResults) {
    var btn = document.getElementById('btnGenerate');
    var badge = document.getElementById('jobBadge');
    var idText = document.getElementById('jobIdText');
    var details = document.getElementById('jobDetails');
    var pollCount = 0;
    lastCompletedCount = 0;
    partialAudioStarted = {};

    if (pollTimer) clearInterval(pollTimer);

    pollTimer = setInterval(function() {
      fetch('/api/v1/quickgen/status/' + jobId)
        .then(function(resp) { return resp.json(); })
        .then(function(data) {
          pollCount++;

          // 实时进度显示
          if (data.status === 'pending' || data.status === 'running') {
            var completed = data.completed_count || 0;
            var total = data.total_count || maxResults;
            var pct = total > 0 ? Math.round((completed / total) * 100) : 0;

            // 进度条 HTML
            var progressHtml = '<div style="width:100%;">';
            progressHtml += '<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">';
            progressHtml += '<span style="color:var(--accent2); font-weight:600;">⏳ 正在生成文章... ' + completed + '/' + total + ' 篇 (' + pct + '%)</span>';
            progressHtml += '</div>';
            // 进度条
            progressHtml += '<div style="width:100%; height:8px; background:var(--bg2); border-radius:4px; overflow:hidden; margin-bottom:8px;">';
            progressHtml += '<div style="width:' + pct + '%; height:100%; background:linear-gradient(90deg, var(--accent), var(--accent2)); border-radius:4px; transition:width 0.5s ease;"></div>';
            progressHtml += '</div>';
            // 正在处理的项目
            if (data.current_projects && data.current_projects.length > 0) {
              progressHtml += '<div style="font-size:12px; color:var(--muted); line-height:1.6;">';
              progressHtml += '🔄 正在处理: ';
              progressHtml += data.current_projects.map(function(p) {
                return '<span style="background:var(--bg2); padding:2px 8px; border-radius:4px; margin:2px; display:inline-block;">' + escapeHtml(p) + '</span>';
              }).join('');
              progressHtml += '</div>';
            }
            progressHtml += '</div>';

            details.innerHTML = progressHtml;
            idText.textContent = '进度: ' + completed + '/' + total + ' 篇';

            // 流式渲染：每完成一篇就显示
            if (completed > lastCompletedCount && data.articles && data.articles.length > 0) {
              lastCompletedCount = completed;
              // 为新完成的文章预生成音频
              data.articles.forEach(function(a, i) {
                var audioKey = jobId + '-' + i;
                if (!partialAudioStarted[audioKey] && a.body && a.word_count > 0) {
                  partialAudioStarted[audioKey] = true;
                }
              });
            }
            return;
          }

          // 任务完成或失败
          clearInterval(pollTimer);
          pollTimer = null;

          if (btn) { btn.disabled = false; btn.style.opacity = '1'; btn.innerHTML = '\u26A1\uFE0F 开始生成'; }

          if (data.status === 'failed') {
            badge.className = 'job-status-badge failed';
            badge.textContent = '失败';
            details.innerHTML = '<span style="color:var(--danger);">❌ ' + escapeHtml(data.error || '未知错误') + '</span>';
            showToast('生成失败: ' + (data.error || '未知错误'), 'error');
            return;
          }

          // 成功
          if (data.articles && data.articles.length > 0) {
            badge.className = 'job-status-badge completed';
            badge.textContent = '已完成';
            idText.textContent = '生成 ' + data.total + ' 篇 · 耗时 ' + data.duration_sec + ' 秒';

            // 存储文章
            var timestamp = new Date().toLocaleString('zh-CN');
            data.articles.forEach(function(a) {
              generatedArticles.unshift({
                title: a.title,
                project_name: a.project_name,
                project_url: a.project_url,
                body: a.body,
                word_count: a.word_count,
                stars_today: a.stars_today,
                language: lang === 'all' ? '多语言' : lang,
                created_at: timestamp
              });
            });

            totalStats.articles += data.articles.length;
            totalStats.projects += data.articles.length;
            totalStats.audio += data.articles.length;
            updateStats();
            renderRecentPodcasts();
            saveToStorage();

            showQuickResults(data);
            showToast('成功生成 ' + data.total + ' 篇文章！耗时 ' + data.duration_sec + ' 秒', 'success');

            // 自动预生成音频：文章生成后立即在后台合成语音
            autoGenerateAudioForArticles(data.articles);

            setTimeout(function() {
              var articlesNav = document.querySelectorAll('.nav-item')[2];
              window.showPage('articles', articlesNav);
            }, 1500);
          } else {
            badge.className = 'job-status-badge completed';
            badge.textContent = '无结果';
            details.innerHTML = '<span style="color:var(--warn);">⚠️ 未发现项目，请稍后重试</span>';
            showToast('未发现项目，请稍后重试', 'error');
          }
        })
        .catch(function(err) {
          // 网络错误时继续轮询（最多10次）
          if (pollCount > 10) {
            clearInterval(pollTimer);
            pollTimer = null;
            if (btn) { btn.disabled = false; btn.style.opacity = '1'; btn.innerHTML = '\u26A1\uFE0F 开始生成'; }
            badge.className = 'job-status-badge failed';
            badge.textContent = '查询失败';
            details.innerHTML = '<span style="color:var(--danger);">❌ 无法查询任务状态: ' + escapeHtml(err.message) + '</span>';
            showToast('查询失败: ' + err.message, 'error');
          }
        });
    }, 2000);
  }

  // ===== Show Quick Results on Generate Page =====
  function showQuickResults(data) {
    var result = document.getElementById('jobResult');
    var badge = document.getElementById('jobBadge');
    var idText = document.getElementById('jobIdText');
    var details = document.getElementById('jobDetails');

    result.classList.add('show');
    badge.className = 'job-status-badge completed';
    badge.textContent = '已完成';
    idText.textContent = '生成 ' + data.total + ' 篇 · 耗时 ' + data.duration_sec + ' 秒';

    var html = '';
    data.articles.forEach(function(a, i) {
      var uid = 'art-' + i;
      // Bug fix #1: Escape all user-controlled content to prevent XSS.
      html += '<div style="border:1px solid var(--rule); border-radius:10px; padding:16px; margin-bottom:12px; background:var(--bg);">' +
        '<div style="display:flex; justify-content:space-between; align-items:start; margin-bottom:8px;">' +
          '<h4 style="font-size:16px; font-weight:700; color:var(--accent); flex:1;">' + (i+1) + '. ' + escapeHtml(a.title) + '</h4>' +
          '<span style="font-size:12px; color:var(--muted); font-family:JetBrainsMono,monospace; white-space:nowrap; margin-left:12px;">' + escapeHtml(a.stars_today) + ' stars/day</span>' +
        '</div>' +
        '<div style="display:flex; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap;">' +
          '<a href="' + escapeHtml(a.project_url) + '" target="_blank" rel="noopener" style="color:var(--accent2); text-decoration:none; font-size:13px;">' + escapeHtml(a.project_name) + '</a>' +
          '<span style="font-size:12px; color:var(--muted);">· ' + escapeHtml(a.word_count) + ' 字</span>' +
          '<button onclick="speakArticle(\'' + uid + '\', this)" style="background:var(--bg2); border:1px solid var(--accent); color:var(--accent); border-radius:6px; padding:4px 12px; cursor:pointer; font-size:13px; font-weight:600; display:flex; align-items:center; gap:4px;">' +
            '<span id="' + uid + '-icon">\u25B6</span> <span id="' + uid + '-label">\u6536\u542C</span>' +
          '</button>' +
          speedBtnHtml() +
          voiceSelectorHtml() +
          volumeControlHtml() +
          continuousPlayBtnHtml() +
        '</div>' +
        '<div id="' + uid + '" style="font-size:14px; line-height:1.8; color:var(--ink); white-space:pre-wrap;">' + escapeHtml(a.body) + '</div>' +
        progressBarHtml(uid) +
      '</div>';
    });
    details.innerHTML = html;
  }
  window.showQuickResults = showQuickResults;

  // ===== Render Articles Page =====
  // Bug fix #5: Populate the articles page with stored generated articles.
  function renderArticlesPage() {
    var container = document.getElementById('articlesContainer');
    if (generatedArticles.length === 0) {
      container.innerHTML =
        '<div class="empty-state">' +
          '<div class="empty-icon">\uD83D\uDCC4</div>' +
          '<p>暂无文章，去「生成内容」页面创建吧！</p>' +
        '</div>';
      return;
    }

    var html = '<div class="article-grid">';
    generatedArticles.forEach(function(a, i) {
      var uid = 'article-' + i;
      var excerpt = a.body.length > 200 ? a.body.substring(0, 200) + '...' : a.body;
      html += '<div class="article-card">' +
        '<span class="lang-badge" style="background:rgba(88,166,255,0.15); color:var(--accent2);">' + escapeHtml(a.language) + '</span>' +
        '<h4>' + escapeHtml(a.title) + '</h4>' +
        '<div class="excerpt">' + escapeHtml(excerpt) + '</div>' +
        '<div class="meta">' +
          '<span>\uD83D\uDCDD ' + escapeHtml(a.word_count) + ' 字</span>' +
          '<span>\u2B50 ' + escapeHtml(a.stars_today) + ' stars/day</span>' +
          '<span>\uD83D\uDD50 ' + escapeHtml(a.created_at) + '</span>' +
        '</div>' +
        '<div style="margin-top:12px; display:flex; gap:8px; align-items:center;">' +
          '<a href="' + escapeHtml(a.project_url) + '" target="_blank" rel="noopener" style="color:var(--accent2); font-size:13px; text-decoration:none;">\uD83D\uDD17 ' + escapeHtml(a.project_name) + '</a>' +
          '<button onclick="speakArticle(\'' + uid + '\', this)" style="background:var(--bg2); border:1px solid var(--accent); color:var(--accent); border-radius:6px; padding:4px 12px; cursor:pointer; font-size:13px; font-weight:600; display:flex; align-items:center; gap:4px;">' +
            '<span id="' + uid + '-icon">\u25B6</span> <span id="' + uid + '-label">\u6536\u542C</span>' +
          '</button>' +
          speedBtnHtml() +
          voiceSelectorHtml() +
          volumeControlHtml() +
          continuousPlayBtnHtml() +
          '<button onclick="toggleArticle(\'' + uid + '\', this)" style="background:transparent; border:none; color:var(--muted); cursor:pointer; font-size:12px; margin-left:auto;" title="\u70B9\u51FB\u5C55\u5F00/\u6536\u8D77\u5168\u6587">\uD83D\uDCD6 \u5168\u6587</button>' +
        '</div>' +
        '<div id="' + uid + '" style="display:none; font-size:14px; line-height:1.8; color:var(--ink); white-space:pre-wrap; margin-top:12px; padding-top:12px; border-top:1px solid var(--rule);">' + escapeHtml(a.body) + '</div>' +
        progressBarHtml(uid) +
      '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }
  window.renderArticlesPage = renderArticlesPage;

  // 渲染文章列表后，静默预加载音频
  function preGenerateAudioForArticlesPage() {
    if (generatedArticles.length === 0) return;
    generatedArticles.forEach(function(a, i) {
      setTimeout(function(idx) {
        var textId = 'article-' + idx;
        var textEl = document.getElementById(textId);
        if (textEl && textEl.textContent.length > 50) {
          var text = textEl.textContent || textEl.innerText;
          preGenerateAudio(textId, text, selectedVoice, playbackRate, true);
        }
      }(i), i * 2000);
    });
  }
  window.preGenerateAudioForArticlesPage = preGenerateAudioForArticlesPage;

  // ===== Render Recent Podcasts on Overview =====
  function renderRecentPodcasts() {
    var container = document.getElementById('recentPodcasts');
    if (!container) return;

    if (generatedArticles.length === 0) {
      container.innerHTML =
        '<div class="recent-empty">' +
          '<p>&#127911; 还没有播客内容，去生成第一篇吧！</p>' +
          '<button class="btn btn-primary" onclick="showPage(\'generate\', this)">&#9889; 立即生成</button>' +
        '</div>';
      return;
    }

    var recent = generatedArticles.slice(0, 3);
    var html = '<div class="recent-list">';
    recent.forEach(function(a, i) {
      var uid = 'recent-' + i;
      var realIdx = generatedArticles.indexOf(a);
      var textId = 'article-' + realIdx;
      var shortTitle = a.title.length > 30 ? a.title.substring(0, 30) + '...' : a.title;
      html += '<div class="recent-item">' +
        '<div class="recent-top">' +
          '<span class="lang-badge" style="background:rgba(88,166,255,0.15); color:var(--accent2);">' + escapeHtml(a.language) + '</span>' +
          '<div class="recent-title">' + escapeHtml(shortTitle) + '</div>' +
        '</div>' +
        '<div class="recent-meta">' +
          '<span>\uD83D\uDCDD ' + escapeHtml(a.word_count) + ' \u5b57</span>' +
          '<span>\u2B50 ' + escapeHtml(a.stars_today) + ' stars/day</span>' +
        '</div>' +
        '<div class="recent-actions">' +
          '<button onclick="speakArticle(\'' + uid + '\', this)" style="background:var(--bg2); border:1px solid var(--accent); color:var(--accent); border-radius:6px; padding:4px 12px; cursor:pointer; font-size:13px; font-weight:600; display:flex; align-items:center; gap:4px;">' +
            '<span id="' + uid + '-icon">\u25B6</span> <span id="' + uid + '-label">\u6536\u542C</span>' +
          '</button>' +
          speedBtnHtml() +
          voiceSelectorHtml() +
          volumeControlHtml() +
          continuousPlayBtnHtml() +
          '<button onclick="toggleArticle(\'' + uid + '\', this)" style="background:transparent; border:none; color:var(--muted); cursor:pointer; font-size:12px; margin-left:auto;" title="\u70B9\u51FB\u5C55\u5F00/\u6536\u8D77\u5168\u6587">\uD83D\uDCD6 \u5168\u6587</button>' +
        '</div>' +
        '<div id="' + uid + '" style="display:none; font-size:14px; line-height:1.8; color:var(--ink); white-space:pre-wrap; margin-top:12px; padding-top:12px; border-top:1px solid var(--rule);">' + escapeHtml(a.body) + '</div>' +
        progressBarHtml(uid) +
      '</div>';
    });
    html += '</div>';
    container.innerHTML = html;
  }
  window.renderRecentPodcasts = renderRecentPodcasts;

  // ===== Audio Player: Howler.js + TTS API, with Web Speech API fallback =====
  var currentHowl = null;          // Howler.js 实例
  var currentUtterance = null;      // Web Speech API 兜底
  var currentBtn = null;
  var currentTextId = null;
  var currentTextLen = 0;
  var progressTimer = null;
  var speakStartTime = 0;

  // 音频缓存：key = textId + voice + speed，value = { blobUrl, blob }
  var audioCache = {};

  // 批量预生成音频：文章生成后自动为每篇文章合成语音
  function autoGenerateAudioForArticles(articles) {
    if (!articles || articles.length === 0) return;

    console.log('[GitCast] 开始预生成 ' + articles.length + ' 篇文章的音频...');

    // 为 showQuickResults 页面的文章（art-0, art-1, ...）预生成
    // TTS API 有服务端缓存，后续 article-* 请求会命中缓存，秒回
    articles.forEach(function(a, i) {
      setTimeout(function() {
        var textId = 'art-' + i;
        var text = a.title + '\n\n' + a.body;
        preGenerateAudio(textId, text, selectedVoice, playbackRate);
      }, i * 2000); // 每篇间隔 2 秒，避免服务器过载
    });
  }
  window.autoGenerateAudioForArticles = autoGenerateAudioForArticles;

  // 预生成音频：文章生成后自动调用 TTS，用户点击时直接播放
  // silent=true 时不显示"合成中"状态（用于页面加载时静默预加载）
  function preGenerateAudio(textId, text, voice, speed, silent) {
    var cacheKey = textId + ':' + voice + ':' + speed;

    // 已缓存则跳过
    if (audioCache[cacheKey]) {
      updateAudioButton(textId, 'ready');
      return;
    }

    // 非静默模式才显示"合成中"（新文章生成时需要给用户反馈）
    if (!silent) {
      updateAudioButton(textId, 'generating');
    }

    fetch('/api/v1/tts/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, voice: voice, speed: speed })
    })
    .then(function(resp) {
      if (!resp.ok) throw new Error('TTS HTTP ' + resp.status);
      return resp.blob();
    })
    .then(function(blob) {
      var blobUrl = URL.createObjectURL(blob);
      audioCache[cacheKey] = { blobUrl: blobUrl, blob: blob };
      updateAudioButton(textId, 'ready');
      console.log('[GitCast] 音频预生成完成:', textId, '(' + (blob.size / 1024).toFixed(0) + ' KB)');
    })
    .catch(function(err) {
      console.warn('[GitCast] 音频预生成失败:', textId, err);
      if (!silent) updateAudioButton(textId, 'normal');
    });
  }
  window.preGenerateAudio = preGenerateAudio;

  // 更新音频按钮状态（不影响正在播放的音频）
  function updateAudioButton(textId, state) {
    var btn = document.querySelector('button[onclick*="speakArticle(\'' + textId + "'");
    if (!btn) return;
    var iconSpan = btn.querySelector('span[id$="-icon"]');
    var labelSpan = btn.querySelector('span[id$="-label"]');

    // 如果正在播放，不覆盖播放状态
    if (currentTextId === textId && currentBtn) return;

    if (state === 'generating') {
      if (iconSpan) iconSpan.textContent = '\u23F3';
      if (labelSpan) labelSpan.textContent = '合成中';
      btn.style.background = 'var(--accent2)';
      btn.style.color = 'var(--bg)';
      btn.style.opacity = '0.7';
      btn.disabled = true;
    } else if (state === 'ready') {
      if (iconSpan) iconSpan.textContent = '\u25B6';
      if (labelSpan) labelSpan.textContent = '播放';
      btn.style.background = 'var(--accent)';
      btn.style.color = 'var(--bg)';
      btn.style.opacity = '1';
      btn.disabled = false;
    } else {
      if (iconSpan) iconSpan.textContent = '\u25B6';
      if (labelSpan) labelSpan.textContent = '\u6536\u542C';
      btn.style.background = 'var(--bg2)';
      btn.style.color = 'var(--accent)';
      btn.style.opacity = '1';
      btn.disabled = false;
    }
  }
  window.updateAudioButton = updateAudioButton;

  // 设置音量（0.0 ~ 3.0），超过 1.0 时通过 Web Audio API 增益
  window.setVolume = function(val) {
    audioVolume = Math.max(0, Math.min(3, parseFloat(val)));
    // 实时调整正在播放的音频
    if (currentHowl) {
      if (audioVolume <= 1.0) {
        currentHowl.volume(audioVolume);
      } else {
        // 超过 1.0 时，Howler volume 设为 1.0，用 GainNode 做额外增益
        currentHowl.volume(1.0);
        applyWebAudioGain(audioVolume);
      }
    }
    // 更新所有音量滑块的值
    document.querySelectorAll('input[type="range"][oninput*="setVolume"]').forEach(function(slider) {
      slider.value = audioVolume;
    });
    // 更新音量图标
    document.querySelectorAll('.vol-icon').forEach(function(icon) {
      if (audioVolume === 0) {
        icon.textContent = '\uD83D\uDD07';
      } else if (audioVolume < 1.0) {
        icon.textContent = '\uD83D\uDD08';
      } else if (audioVolume < 2.0) {
        icon.textContent = '\uD83D\uDD09';
      } else {
        icon.textContent = '\uD83D\uDD0A';
      }
    });
    // 持久化
    try { localStorage.setItem('gitcast_volume', String(audioVolume)); } catch(e) {}
  };

  // Web Audio API 增益：当音量超过 1.0 时，通过 GainNode 放大
  var audioCtx = null;
  var gainNode = null;
  function applyWebAudioGain(volume) {
    try {
      if (!audioCtx) {
        var AC = window.AudioContext || window.webkitAudioContext;
        if (!AC) return;
        audioCtx = new AC();
        gainNode = audioCtx.createGain();
        gainNode.connect(audioCtx.destination);
      }
      if (gainNode) {
        gainNode.gain.value = volume;
      }
    } catch(e) {
      console.warn('[GitCast] Web Audio gain failed:', e);
    }
  }

  // 切换连续播放模式
  window.toggleContinuousPlay = function(btn) {
    continuousPlay = !continuousPlay;
    try { localStorage.setItem('gitcast_continuous', String(continuousPlay)); } catch(e) {}

    // 更新所有连续播放按钮的样式
    document.querySelectorAll('button[onclick*="toggleContinuousPlay"]').forEach(function(b) {
      if (continuousPlay) {
        b.style.background = 'var(--accent)';
        b.style.color = 'var(--bg)';
        b.style.borderColor = 'var(--accent)';
        b.innerHTML = '\u2705 \u8FDE\u64AD';  // ✅ 连播
      } else {
        b.style.background = 'var(--bg2)';
        b.style.color = 'var(--muted)';
        b.style.borderColor = 'var(--rule)';
        b.innerHTML = '\u26F1 \u8FDE\u64AD';  // ⛱ 连播
      }
    });

    showToast(continuousPlay ? '已开启连续播放' : '已关闭连续播放', 'info');
  };

  // 构建播放队列：收集当前页面上所有文章的 textId
  function buildPlayQueue(currentTextId) {
    playQueue = [];
    // 查找所有文章正文容器
    var textEls = document.querySelectorAll('[id^="art-"], [id^="article-"], [id^="recent-"]');
    textEls.forEach(function(el) {
      var elId = el.id;
      var elText = el.textContent || el.innerText;
      if (elText.length > 50) {
        playQueue.push(elId);
      }
    });
    // 定位当前播放的索引
    currentQueueIndex = playQueue.indexOf(currentTextId);
  }

  // 播放队列中的下一首
  function playNextInQueue() {
    if (!continuousPlay || playQueue.length === 0) return;

    currentQueueIndex++;
    if (currentQueueIndex >= playQueue.length) {
      // 播放完毕，重置
      currentQueueIndex = -1;
      playQueue = [];
      showToast('全部文章播放完毕', 'info');
      return;
    }

    var nextTextId = playQueue[currentQueueIndex];
    var nextBtn = document.querySelector('button[onclick*="speakArticle(\'' + nextTextId + "')");

    if (nextBtn) {
      // 短暂延迟后自动播放下一篇
      setTimeout(function() {
        showToast('正在播放下一篇...', 'info');
        window.speakArticle(nextTextId, nextBtn);
      }, 500);
    } else {
      // 找不到按钮，尝试下一篇
      playNextInQueue();
    }
  }
  window.playNextInQueue = playNextInQueue;

  // 切换倍速
  window.cycleSpeed = function(btn) {
    var currentIdx = speedOptions.indexOf(playbackRate);
    var nextIdx = (currentIdx + 1) % speedOptions.length;
    playbackRate = speedOptions[nextIdx];

    // 更新所有倍速按钮显示
    document.querySelectorAll('button[onclick*="cycleSpeed"]').forEach(function(b) {
      b.textContent = speedLabels[playbackRate];
    });

    // 如果正在播放
    if (currentHowl) {
      // howler.js 支持实时变速，无需重启
      currentHowl.rate(playbackRate);
    } else if (currentUtterance && currentTextId && currentBtn) {
      // Web Speech API 兜底：需要重启
      var btnToRestart = currentBtn;
      var textIdToRestart = currentTextId;
      window.speechSynthesis.cancel();
      stopSpeaking(btnToRestart);
      setTimeout(function() {
        window.speakArticle(textIdToRestart, btnToRestart);
      }, 100);
    }

    // 倍速改变后，重新预生成当前可见文章的音频
    regenerateVisibleAudio();
  };

  // 切换音色
  window.changeVoice = function(select) {
    selectedVoice = select.value;
    // 同步所有音色选择器
    document.querySelectorAll('select[onchange*="changeVoice"]').forEach(function(s) {
      s.value = selectedVoice;
    });

    // 音色改变后，重新预生成当前可见文章的音频
    regenerateVisibleAudio();
  };

  // 重新预生成当前页面上可见文章的音频（音色/倍速改变时调用）
  function regenerateVisibleAudio() {
    // 查找当前页面上所有文章正文容器
    var textEls = document.querySelectorAll('[id^="art-"], [id^="article-"], [id^="recent-"]');
    textEls.forEach(function(el) {
      var elId = el.id;
      var elText = el.textContent || el.innerText;
      if (elText.length < 50) return; // 跳过非文章容器

      // 检查新设置是否已有缓存
      var newKey = elId + ':' + selectedVoice + ':' + playbackRate;
      if (audioCache[newKey]) {
        // 已有缓存，直接标记为就绪
        updateAudioButton(elId, 'ready');
      } else {
        // 需要重新生成（静默模式，不显示"合成中"）
        preGenerateAudio(elId, elText, selectedVoice, playbackRate, true);
      }
    });
  }
  window.regenerateVisibleAudio = regenerateVisibleAudio;

  // 展开/收起全文
  window.toggleArticle = function(textId, btn) {
    var textEl = document.getElementById(textId);
    if (!textEl) return;
    var isHidden = textEl.style.display === 'none' || !textEl.style.display;
    if (isHidden) {
      textEl.style.display = 'block';
      if (btn) {
        btn.innerHTML = '\uD83D\uDCD5 \u6536\u8D77';
        btn.style.color = 'var(--accent)';
      }
    } else {
      textEl.style.display = 'none';
      if (btn) {
        btn.innerHTML = '\uD83D\uDCD6 \u5168\u6587';
        btn.style.color = 'var(--muted)';
      }
    }
  };

  // 生成音色选择器 HTML
  function voiceSelectorHtml() {
    var opts = voiceOptions.map(function(v) {
      return '<option value="' + v.key + '"' + (v.key === selectedVoice ? ' selected' : '') + '>' + v.label + '</option>';
    }).join('');
    return '<select onchange="event.stopPropagation(); changeVoice(this)" ' +
      'style="background:var(--bg2); border:1px solid var(--rule); color:var(--muted); ' +
      'border-radius:6px; padding:3px 8px; cursor:pointer; font-size:12px; ' +
      'font-family:WorkSans,sans-serif; outline:none;" title="选择音色">' + opts + '</select>';
  }

  // 生成倍速按钮 HTML
  function speedBtnHtml() {
    return '<button onclick="event.stopPropagation(); cycleSpeed(this)" ' +
      'style="background:var(--bg2); border:1px solid var(--rule); color:var(--muted); ' +
      'border-radius:6px; padding:4px 10px; cursor:pointer; font-size:13px; ' +
      'font-family:JetBrainsMono,monospace; font-weight:600; min-width:48px; text-align:center;" ' +
      'title="点击切换播放速度">' + speedLabels[playbackRate] + '</button>';
  }

  // 生成音量控制 HTML（支持 0-3 倍放大）
  function volumeControlHtml() {
    var icon = audioVolume === 0 ? '\uD83D\uDD07' : audioVolume < 1.0 ? '\uD83D\uDD08' : audioVolume < 2.0 ? '\uD83D\uDD09' : '\uD83D\uDD0A';
    var volPct = Math.round(audioVolume * 100);
    return '<span style="display:inline-flex; align-items:center; gap:3px; background:var(--bg2); ' +
      'border:1px solid var(--rule); border-radius:6px; padding:2px 6px;" title="音量（可放大至 3 倍）">' +
      '<span class="vol-icon" style="font-size:13px; cursor:pointer;" onclick="setVolume(' + (audioVolume > 0 ? '0' : '1.5') + ')">' + icon + '</span>' +
      '<input type="range" min="0" max="3" step="0.1" value="' + audioVolume + '" ' +
        'oninput="event.stopPropagation(); setVolume(this.value)" ' +
        'style="width:60px; height:4px; cursor:pointer; accent-color:var(--accent); vertical-align:middle;" />' +
      '<span style="font-size:10px; color:var(--muted); font-family:JetBrainsMono,monospace; min-width:28px;">' + volPct + '%</span>' +
      '</span>';
  }

  // 生成连续播放按钮 HTML
  function continuousPlayBtnHtml() {
    var bg = continuousPlay ? 'var(--accent)' : 'var(--bg2)';
    var color = continuousPlay ? 'var(--bg)' : 'var(--muted)';
    var border = continuousPlay ? 'var(--accent)' : 'var(--rule)';
    var icon = continuousPlay ? '\u2705' : '\u26F1';  // ✅ / ⛱
    return '<button onclick="event.stopPropagation(); toggleContinuousPlay(this)" ' +
      'style="background:' + bg + '; border:1px solid ' + border + '; color:' + color + '; ' +
      'border-radius:6px; padding:4px 10px; cursor:pointer; font-size:13px; font-weight:500;" ' +
      'title="开启后，当前文章播完自动播放下一篇">' + icon + ' \u8FDE\u64AD</button>';
  }

  // 生成进度条 HTML
  function progressBarHtml(uid) {
    return '<div id="' + uid + '-progress" style="display:none; margin-top:10px;">' +
      '<div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">' +
        '<div style="flex:1; height:6px; background:var(--bg); border-radius:3px; overflow:hidden;">' +
          '<div id="' + uid + '-bar" style="width:0%; height:100%; background:linear-gradient(90deg, var(--accent), var(--accent2)); border-radius:3px; transition:width 0.3s ease;"></div>' +
        '</div>' +
        '<span id="' + uid + '-time" style="font-size:11px; color:var(--muted); font-family:JetBrainsMono,monospace; white-space:nowrap; min-width:60px; text-align:right;">0:00 / 0:00</span>' +
      '</div>' +
    '</div>';
  }

  // 格式化时间
  function formatTime(seconds) {
    var m = Math.floor(seconds / 60);
    var s = Math.floor(seconds % 60);
    return m + ':' + (s < 10 ? '0' : '') + s;
  }

  // 设置按钮状态
  function setBtnState(btn, state) {
    if (!btn) return;
    var iconSpan = btn.querySelector('span[id$="-icon"]');
    var labelSpan = btn.querySelector('span[id$="-label"]');
    if (state === 'loading') {
      if (iconSpan) iconSpan.textContent = '\u23F3';
      if (labelSpan) labelSpan.textContent = '生成中';
      btn.style.background = 'var(--accent2)';
      btn.style.color = 'var(--bg)';
    } else if (state === 'playing') {
      if (iconSpan) iconSpan.textContent = '\u23F8';
      if (labelSpan) labelSpan.textContent = '停止';
      btn.style.background = 'var(--accent)';
      btn.style.color = 'var(--bg)';
    } else {
      if (iconSpan) iconSpan.textContent = '\u25B6';
      if (labelSpan) labelSpan.textContent = '\u6536\u542C';
      btn.style.background = 'var(--bg2)';
      btn.style.color = 'var(--accent)';
    }
  }

  // 主播放函数：先检查缓存，再尝试 TTS API + howler.js，失败则回退到 Web Speech API
  window.speakArticle = function(textId, btn) {
    var textEl = document.getElementById(textId);
    if (!textEl) return;

    // 如果正在播放/加载且点击的是同一个按钮，停止
    if (currentBtn === btn) {
      stopSpeaking(btn);
      // 手动停止时清除队列，不自动播放下一篇
      playQueue = [];
      currentQueueIndex = -1;
      return;
    }

    // 停止之前的播放
    if (currentBtn) stopSpeaking(currentBtn);

    var text = textEl.textContent || textEl.innerText;
    currentTextLen = text.length;
    currentBtn = btn;
    currentTextId = textId;

    // 构建播放队列（连续播放模式）
    if (continuousPlay) {
      buildPlayQueue(textId);
    }

    // 显示进度条
    var progressEl = document.getElementById(textId + '-progress');
    var barEl = document.getElementById(textId + '-bar');
    var timeEl = document.getElementById(textId + '-time');
    if (progressEl) {
      progressEl.style.display = 'block';
    }

    // 1. 先检查音频缓存
    var cacheKey = textId + ':' + selectedVoice + ':' + playbackRate;
    if (audioCache[cacheKey]) {
      // 缓存命中，直接播放
      if (timeEl) timeEl.textContent = '准备播放...';
      playWithHowler(audioCache[cacheKey].blobUrl, btn, textId, progressEl, barEl, timeEl);
      return;
    }

    // 2. 缓存未命中，实时生成
    setBtnState(btn, 'loading');
    if (timeEl) timeEl.textContent = '正在生成语音...';

    fetch('/api/v1/tts/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text,
        voice: selectedVoice,
        speed: playbackRate
      })
    })
    .then(function(resp) {
      if (!resp.ok) throw new Error('TTS HTTP ' + resp.status);
      return resp.blob();
    })
    .then(function(blob) {
      // 检查是否已被取消
      if (currentBtn !== btn) return;
      var audioUrl = URL.createObjectURL(blob);
      // 存入缓存
      audioCache[cacheKey] = { blobUrl: audioUrl, blob: blob };
      playWithHowler(audioUrl, btn, textId, progressEl, barEl, timeEl);
    })
    .catch(function(err) {
      console.warn('TTS API failed, falling back to Web Speech API:', err);
      if (currentBtn !== btn) return;
      if (timeEl) timeEl.textContent = '使用浏览器语音...';
      playWithWebSpeech(text, btn, textId, progressEl, barEl, timeEl);
    });
  };

  // 使用 Howler.js 播放（TTS 生成的 MP3）
  function playWithHowler(audioUrl, btn, textId, progressEl, barEl, timeEl) {
    if (typeof Howl === 'undefined') {
      console.warn('Howler.js not loaded, falling back to Web Speech API');
      playWithWebSpeech(
        document.getElementById(textId).textContent,
        btn, textId, progressEl, barEl, timeEl
      );
      return;
    }

    var howl = new Howl({
      src: [audioUrl],
      format: ['mp3'],
      rate: playbackRate,
      volume: Math.min(audioVolume, 1.0),
      onplay: function() {
        // 音量超过 1.0 时，通过 Web Audio API GainNode 做额外增益
        if (audioVolume > 1.0) {
          applyWebAudioGain(audioVolume);
        }
        setBtnState(btn, 'playing');
        speakStartTime = Date.now();
        // 启动进度更新定时器
        if (progressTimer) clearInterval(progressTimer);
        progressTimer = setInterval(function() {
          if (!currentHowl) {
            clearInterval(progressTimer);
            progressTimer = null;
            return;
          }
          var dur = howl.duration();
          var seek = howl.seek();
          if (dur > 0 && barEl) {
            var percent = Math.min((seek / dur) * 100, 100);
            barEl.style.width = percent + '%';
          }
          if (timeEl && dur > 0) {
            timeEl.textContent = formatTime(seek) + ' / ' + formatTime(dur);
          }
        }, 250);
      },
      onend: function() {
        if (barEl) barEl.style.width = '100%';
        var dur = howl.duration();
        if (timeEl && dur > 0) {
          timeEl.textContent = formatTime(dur) + ' / ' + formatTime(dur);
        }
        if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }
        setTimeout(function() {
          if (progressEl) progressEl.style.display = 'none';
          if (barEl) barEl.style.width = '0%';
        }, 2000);
        stopSpeaking(btn);
        URL.revokeObjectURL(audioUrl);

        // 连续播放：自动播放下一篇
        if (continuousPlay && playQueue.length > 0) {
          playNextInQueue();
        }
      },
      onloaderror: function(id, err) {
        console.error('Howl load error:', err);
        if (currentBtn !== btn) return;
        if (timeEl) timeEl.textContent = '加载失败，使用浏览器语音...';
        playWithWebSpeech(
          document.getElementById(textId).textContent,
          btn, textId, progressEl, barEl, timeEl
        );
      },
      onplayerror: function(id, err) {
        console.error('Howl play error:', err);
        stopSpeaking(btn);
        showToast('音频播放失败', 'error');
      }
    });

    currentHowl = howl;
    howl.play();
  }

  // 使用 Web Speech API 播放（兜底方案）
  function playWithWebSpeech(text, btn, textId, progressEl, barEl, timeEl) {
    if (!window.speechSynthesis) {
      setBtnState(btn, 'normal');
      if (progressEl) progressEl.style.display = 'none';
      showToast('浏览器不支持语音合成', 'error');
      return;
    }

    var utterance = new SpeechSynthesisUtterance(text);
    var voices = window.speechSynthesis.getVoices();
    var zhVoice = voices.find(function(v) { return v.lang.startsWith('zh'); });
    if (zhVoice) utterance.voice = zhVoice;
    utterance.lang = 'zh-CN';
    utterance.rate = playbackRate;
    utterance.pitch = 1.0;
    utterance.volume = audioVolume;

    setBtnState(btn, 'playing');
    speakStartTime = Date.now();

    // 估算总时长（中文约 4 字/秒 * rate）
    var estimatedDuration = text.length / (4 * playbackRate);

    // 用 onboundary 更新进度
    utterance.onboundary = function(event) {
      if (event.charIndex !== undefined && text.length > 0) {
        var percent = Math.min((event.charIndex / text.length) * 100, 100);
        if (barEl) barEl.style.width = percent + '%';
        var elapsed = (Date.now() - speakStartTime) / 1000;
        if (timeEl) {
          timeEl.textContent = formatTime(elapsed) + ' / ' + formatTime(estimatedDuration);
        }
      }
    };

    // 定时更新进度（onboundary 在部分浏览器不触发，作为兜底）
    if (progressTimer) clearInterval(progressTimer);
    progressTimer = setInterval(function() {
      if (!currentUtterance) {
        clearInterval(progressTimer);
        progressTimer = null;
        return;
      }
      var elapsed = (Date.now() - speakStartTime) / 1000;
      var percent = Math.min((elapsed / estimatedDuration) * 100, 99);
      if (barEl && parseFloat(barEl.style.width) < percent) {
        barEl.style.width = percent + '%';
      }
      if (timeEl) {
        timeEl.textContent = formatTime(elapsed) + ' / ' + formatTime(estimatedDuration);
      }
    }, 500);

    utterance.onend = function() {
      if (barEl) barEl.style.width = '100%';
      var elapsed = (Date.now() - speakStartTime) / 1000;
      if (timeEl) timeEl.textContent = formatTime(elapsed) + ' / ' + formatTime(elapsed);
      if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }
      setTimeout(function() {
        if (progressEl) progressEl.style.display = 'none';
        if (barEl) barEl.style.width = '0%';
      }, 2000);
      stopSpeaking(btn);

      // 连续播放：自动播放下一篇
      if (continuousPlay && playQueue.length > 0) {
        playNextInQueue();
      }
    };
    utterance.onerror = function() {
      if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }
      if (progressEl) progressEl.style.display = 'none';
      stopSpeaking(btn);
      showToast('语音合成失败', 'error');
    };

    currentUtterance = utterance;
    window.speechSynthesis.speak(utterance);
  }

  // 停止播放并重置按钮状态
  function stopSpeaking(btn) {
    // 停止 howler
    if (currentHowl) {
      try { currentHowl.stop(); currentHowl.unload(); } catch(e) {}
      currentHowl = null;
    }
    // 停止 Web Speech
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    currentUtterance = null;
    // 清除定时器
    if (progressTimer) { clearInterval(progressTimer); progressTimer = null; }
    // 重置按钮
    if (btn) setBtnState(btn, 'normal');
    // 清除状态
    currentBtn = null;
    currentTextId = null;
  }

  // Preload voice list for Web Speech API fallback
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = function() {
      window.speechSynthesis.getVoices();
    };
  }

  // Bug fix #2: Removed dead showDemoJobResult function that referenced
  // the undefined showJobResult. It was never called anywhere.

  // ===== Check API Status =====
  fetch('/api/v1/health')
    .then(function(r) {
      if (r.ok) {
        document.getElementById('apiStatusDot').classList.remove('off');
        document.getElementById('apiStatusText').textContent = 'API 运行中';
      }
    })
    .catch(function() {
      document.getElementById('apiStatusDot').classList.add('off');
      document.getElementById('apiStatusText').textContent = 'API 未连接';
    });

})();
