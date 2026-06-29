// GitCast Service Worker - PWA 离线缓存
var CACHE_NAME = 'gitcast-v25';
var CACHE_URLS = [
  './gitcast-console.html',
  './assets/app.js',
  './manifest.json',
  './icons/icon-192.png',
  './icons/icon-512.png',
  './icons/apple-touch-icon.png',
  './_shared/js/echarts.min.js',
  './_shared/js/howler.min.js'
];

// 安装：预缓存核心资源
self.addEventListener('install', function(e) {
  e.waitUntil(
    caches.open(CACHE_NAME).then(function(cache) {
      return cache.addAll(CACHE_URLS).catch(function(err) {
        console.warn('[SW] 部分资源缓存失败，忽略:', err);
      });
    })
  );
  self.skipWaiting();
});

// 激活：清理旧缓存
self.addEventListener('activate', function(e) {
  e.waitUntil(
    caches.keys().then(function(names) {
      return Promise.all(
        names.filter(function(name) { return name !== CACHE_NAME; })
             .map(function(name) { return caches.delete(name); })
      );
    })
  );
  self.clients.claim();
});

// 请求拦截：网络优先，失败回退缓存
self.addEventListener('fetch', function(e) {
  var url = new URL(e.request.url);

  // API 请求：始终走网络，不缓存
  if (url.pathname.indexOf('/api/') !== -1) {
    return;
  }

  // 音频文件：不缓存（太大）
  if (url.pathname.indexOf('/audio/') !== -1 || url.pathname.indexOf('/tts/') !== -1) {
    return;
  }

  e.respondWith(
    fetch(e.request)
      .then(function(resp) {
        // 成功获取：缓存副本
        if (resp && resp.status === 200 && resp.type === 'basic') {
          var respClone = resp.clone();
          caches.open(CACHE_NAME).then(function(cache) {
            cache.put(e.request, respClone);
          });
        }
        return resp;
      })
      .catch(function() {
        // 网络失败：回退缓存
        return caches.match(e.request).then(function(cached) {
          return cached || caches.match('./gitcast-console.html');
        });
      })
  );
});
