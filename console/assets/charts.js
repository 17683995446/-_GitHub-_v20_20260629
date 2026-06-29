(function() {
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var accent2 = style.getPropertyValue('--accent2').trim();
  var accent3 = style.getPropertyValue('--accent3').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var bg2 = style.getPropertyValue('--bg2').trim();

  // ===== Demo data (API not connected) =====
  var demoStats = {
    articles: 42, audio: 38, projects: 56, publishes: 31,
    articlesToday: 5
  };

  // ===== Init stat numbers =====
  document.getElementById('stat-articles').textContent = demoStats.articles;
  document.getElementById('stat-audio').textContent = demoStats.audio;
  document.getElementById('stat-projects').textContent = demoStats.projects;
  document.getElementById('stat-publish').textContent = demoStats.publishes;

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
  window.showPage = function(pageName) {
    document.querySelectorAll('.page').forEach(function(p) { p.classList.remove('active'); });
    document.getElementById('page-' + pageName).classList.add('active');
    document.querySelectorAll('.nav-item').forEach(function(n) { n.classList.remove('active'); });
    event.currentTarget.classList.add('active');
  };

  // ===== Chip Selection =====
  document.querySelectorAll('#langChips .chip').forEach(function(chip) {
    chip.addEventListener('click', function() {
      if (chip.dataset.lang === 'all') {
        document.querySelectorAll('#langChips .chip').forEach(function(c) {
          c.classList.remove('selected');
        });
        chip.classList.add('selected');
      } else {
        document.querySelector('#langChips .chip[data-lang="all"]').classList.remove('selected');
        chip.classList.toggle('selected');
      }
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

  // ===== Trigger Pipeline =====
  window.triggerPipeline = function() {
    var langs = [];
    document.querySelectorAll('#langChips .chip.selected').forEach(function(c) {
      langs.push(c.dataset.lang);
    });

    if (langs.length === 0) {
      showToast('请至少选择一个编程语言', 'error');
      return;
    }

    var maxResults = 5;
    document.querySelectorAll('#maxResultsGroup .toggle-item').forEach(function(i) {
      if (i.classList.contains('active')) maxResults = parseInt(i.dataset.value);
    });

    var genAudio = document.getElementById('optAudio').checked;
    var doPublish = document.getElementById('optPublish').checked;
    var skipExisting = document.getElementById('optSkip').checked;

    showToast('正在发现项目并生成文章...', 'info');

    // 禁用按钮防止重复点击
    var btn = document.querySelector('.btn-primary.btn-lg');
    if (btn) { btn.disabled = true; btn.style.opacity = '0.6'; btn.textContent = '生成中...'; }

    // 调用快速生成 API（不需要数据库）
    fetch('/api/v1/quickgen/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        language: langs[0] === 'all' ? 'python' : langs[0],
        max_results: maxResults
      })
    })
    .then(function(resp) {
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      return resp.json();
    })
    .then(function(data) {
      var btn2 = document.querySelector('.btn-primary.btn-lg');
      if (btn2) { btn2.disabled = false; btn2.style.opacity = '1'; btn2.innerHTML = '\u26A1\uFE0F 开始生成'; }

      if (data.articles && data.articles.length > 0) {
        showQuickResults(data);
        showToast('成功生成 ' + data.total + ' 篇文章！耗时 ' + data.duration_sec + ' 秒', 'success');
      } else {
        showToast('未发现项目，请稍后重试', 'error');
      }
    })
    .catch(function(err) {
      var btn3 = document.querySelector('.btn-primary.btn-lg');
      if (btn3) { btn3.disabled = false; btn3.style.opacity = '1'; btn3.innerHTML = '\u26A1\uFE0F 开始生成'; }
      showToast('API 错误: ' + err.message, 'error');
    });
  };

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
      html += '<div style="border:1px solid var(--rule); border-radius:10px; padding:16px; margin-bottom:12px; background:var(--bg);">' +
        '<div style="display:flex; justify-content:space-between; align-items:start; margin-bottom:8px;">' +
          '<h4 style="font-size:16px; font-weight:700; color:var(--accent); flex:1;">' + (i+1) + '. ' + a.title + '</h4>' +
          '<span style="font-size:12px; color:var(--muted); font-family:JetBrainsMono,monospace; white-space:nowrap; margin-left:12px;">' + a.stars_today + ' stars/day</span>' +
        '</div>' +
        '<div style="display:flex; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap;">' +
          '<a href="' + a.project_url + '" target="_blank" style="color:var(--accent2); text-decoration:none; font-size:13px;">' + a.project_name + '</a>' +
          '<span style="font-size:12px; color:var(--muted);">· ' + a.word_count + ' 字</span>' +
          '<button onclick="speakArticle(\'' + uid + '\', this)" style="background:var(--bg2); border:1px solid var(--accent); color:var(--accent); border-radius:6px; padding:4px 12px; cursor:pointer; font-size:13px; font-weight:600; display:flex; align-items:center; gap:4px;">' +
            '<span id="' + uid + '-icon">\u25B6</span> <span id="' + uid + '-label">\u6536\u542C</span>' +
          '</button>' +
        '</div>' +
        '<div id="' + uid + '" style="font-size:14px; line-height:1.8; color:var(--ink); white-space:pre-wrap;">' + a.body + '</div>' +
      '</div>';
    });
    details.innerHTML = html;
  };

  // ===== Web Speech API: 浏览器内置语音合成 =====
  var currentUtterance = null;
  var currentBtn = null;

  window.speakArticle = function(textId, btn) {
    var textEl = document.getElementById(textId);
    if (!textEl) return;

    // 如果正在朗读且点击的是同一个按钮，则停止
    if (currentUtterance && currentBtn === btn) {
      window.speechSynthesis.cancel();
      stopSpeaking(btn);
      return;
    }

    // 停止之前的朗读
    if (currentUtterance) {
      window.speechSynthesis.cancel();
      if (currentBtn) stopSpeaking(currentBtn);
    }

    var text = textEl.textContent || textEl.innerText;
    var utterance = new SpeechSynthesisUtterance(text);

    // 尝试选择中文语音
    var voices = window.speechSynthesis.getVoices();
    var zhVoice = voices.find(function(v) { return v.lang.startsWith('zh'); });
    if (zhVoice) utterance.voice = zhVoice;
    utterance.lang = 'zh-CN';
    utterance.rate = 1.0;
    utterance.pitch = 1.0;

    utterance.onend = function() {
      stopSpeaking(btn);
    };
    utterance.onerror = function() {
      stopSpeaking(btn);
      showToast('语音合成失败，请检查浏览器支持', 'error');
    };

    currentUtterance = utterance;
    currentBtn = btn;
    btn.querySelector('span[id$="-icon"]').textContent = '\u23F8';
    btn.querySelector('span[id$="-label"]').textContent = '\u505C\u6B62';
    btn.style.background = 'var(--accent)';
    btn.style.color = 'var(--bg)';

    window.speechSynthesis.speak(utterance);
  };

  function stopSpeaking(btn) {
    if (!btn) return;
    var iconId = btn.querySelector('span[id$="-icon"]').id;
    var labelId = btn.querySelector('span[id$="-label"]').id;
    var iconEl = document.getElementById(iconId);
    var labelEl = document.getElementById(labelId);
    if (iconEl) iconEl.textContent = '\u25B6';
    if (labelEl) labelEl.textContent = '\u6536\u542C';
    btn.style.background = 'var(--bg2)';
    btn.style.color = 'var(--accent)';
    currentUtterance = null;
    currentBtn = null;
  }

  // 预加载语音列表（部分浏览器需要异步加载）
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.onvoiceschanged = function() {
      window.speechSynthesis.getVoices();
    };
  }

  function showDemoJobResult() {
    var demoJobId = 'demo-' + Date.now().toString(36);
    showJobResult(demoJobId, 'running');

    // Simulate progress
    var steps = [
      '正在扫描 GitHub Trending...',
      '发现 5 个高价值项目，开始处理...',
      '正在生成文章 (1/5)...',
      '正在合成音频 (3/5)...',
      '正在发布到喜马拉雅、小宇宙...',
      '管线执行完成！'
    ];
    var stepIndex = 0;
    var interval = setInterval(function() {
      if (stepIndex < steps.length - 1) {
        document.getElementById('jobDetails').textContent = steps[stepIndex];
        stepIndex++;
      } else {
        clearInterval(interval);
        showJobResult(demoJobId, 'completed');
        document.getElementById('jobDetails').innerHTML =
          '<span style="color:var(--accent);">模拟完成！发现 5 个项目，生成 5 篇文章，合成 5 条音频，发布到 4 个平台。</span><br>' +
          '<span style="font-size:12px; color:var(--muted);">提示：连接真实 API 后将显示实际结果。</span>';
      }
    }, 1500);
  }

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
