/**
 * Tree-sitter AST 代码分析器
 * 在浏览器/WebView 中对源代码进行真正的 AST 解析
 * 提取函数签名、类定义、方法签名等结构化信息
 */
(function(global) {
  'use strict';

  var Parser = null;
  var languages = {};
  var initialized = false;
  var initPromise = null;

  // 语言到 WASM 文件路径的映射
  var LANG_MAP = {
    python: { wasm: 'tree-sitter-python.wasm', exts: ['py'] },
    javascript: { wasm: 'tree-sitter-javascript.wasm', exts: ['js', 'mjs', 'cjs'] },
    typescript: { wasm: 'tree-sitter-typescript.wasm', exts: ['ts', 'tsx'] },
    go: { wasm: 'tree-sitter-go.wasm', exts: ['go'] },
    rust: { wasm: 'tree-sitter-rust.wasm', exts: ['rs'] }
  };

  // 语言扩展名查找
  function detectLanguage(filePath) {
    var ext = filePath.split('.').pop().toLowerCase();
    for (var lang in LANG_MAP) {
      if (LANG_MAP[lang].exts.indexOf(ext) >= 0) return lang;
    }
    return null;
  }

  // WASM 基础路径
  function getWasmBasePath() {
    var scripts = document.querySelectorAll('script[src]');
    for (var i = 0; i < scripts.length; i++) {
      var src = scripts[i].src;
      if (src.indexOf('tree-sitter-analyzer') >= 0) {
        return src.substring(0, src.lastIndexOf('/') + 1) + 'tree-sitter/';
      }
    }
    return './tree-sitter/';
  }

  // 初始化
  async function init() {
    if (initialized) return;
    if (initPromise) return initPromise;

    initPromise = (async function() {
      try {
        // 尝试多种方式加载 web-tree-sitter
        // 方式1：已经在全局可用
        if (typeof global.WebTreeSitter !== 'undefined' && global.WebTreeSitter.init) {
          Parser = global.WebTreeSitter;
        }

        // 方式2：动态加载 ES Module
        if (!Parser) {
          try {
            var basePath = getWasmBasePath();
            var mod = await import(basePath + 'web-tree-sitter.js');
            Parser = mod.default || mod.Parser || mod;
          } catch(e) {
            // 方式3：用 script 标签加载
            if (!global.WebTreeSitter) {
              await new Promise(function(resolve, reject) {
                var script = document.createElement('script');
                script.src = getWasmBasePath() + 'web-tree-sitter.js';
                script.onload = resolve;
                script.onerror = reject;
                document.head.appendChild(script);
              });
            }
            Parser = global.WebTreeSitter || global.Parser;
          }
        }

        if (!Parser || !Parser.init) {
          console.warn('[tree-sitter] Parser not available, falling back to regex');
          initialized = true;
          return false;
        }

        await Parser.init({
          locateFile: function(path) {
            return getWasmBasePath() + path;
          }
        });

        // 预加载常用语言
        var basePath = getWasmBasePath();
        for (var langName in LANG_MAP) {
          try {
            var wasmUrl = basePath + LANG_MAP[langName].wasm;
            var resp = await fetch(wasmUrl);
            if (resp.ok) {
              var wasmBuf = await resp.arrayBuffer();
              var lang = await Parser.Language.load(wasmBuf);
              languages[langName] = lang;
            }
          } catch(e) {
            console.warn('[tree-sitter] Failed to load language ' + langName + ':', e.message);
          }
        }

        initialized = true;
        console.log('[tree-sitter] Initialized with', Object.keys(languages).length, 'languages');
        return Object.keys(languages).length > 0;
      } catch(e) {
        console.warn('[tree-sitter] Init failed, will use regex fallback:', e.message);
        initialized = true;
        return false;
      }
    })();

    return initPromise;
  }

  // AST 节点类型到结构化信息的关键模式
  var NODE_PATTERNS = {
    python: {
      functions: ['function_definition', 'decorated_definition'],
      classes: ['class_definition'],
      imports: ['import_statement', 'import_from_statement'],
      assignments: ['assignment']
    },
    javascript: {
      functions: ['function_declaration', 'generator_function_declaration', 'arrow_function'],
      classes: ['class_declaration', 'class'],
      imports: ['import_statement'],
      exports: ['export_statement']
    },
    typescript: {
      functions: ['function_declaration', 'generator_function_declaration', 'arrow_function'],
      classes: ['class_declaration', 'class'],
      interfaces: ['interface_declaration'],
      types: ['type_alias_declaration'],
      imports: ['import_statement'],
      exports: ['export_statement']
    },
    go: {
      functions: ['function_declaration', 'method_declaration'],
      types: ['type_declaration'],
      structs: ['struct_type'],
      interfaces: ['interface_type'],
      imports: ['import_declaration']
    },
    rust: {
      functions: ['function_item', 'function_signature_item'],
      structs: ['struct_item'],
      enums: ['enum_item'],
      traits: ['trait_item'],
      impls: ['impl_item'],
      macros: ['macro_definition']
    }
  };

  // 提取节点签名文本（函数名、类名、参数等）
  function extractSignature(node, sourceLines) {
    var startRow = node.startPosition.row;
    var endRow = Math.min(startRow + 3, sourceLines.length - 1); // 签名最多取 3 行

    // 尝试找到函数/类名
    var name = '';
    for (var i = 0; i < node.childCount; i++) {
      var child = node.child(i);
      if (child.type === 'identifier' || child.type === 'name' || child.type === 'property_identifier') {
        name = sourceLines[child.startPosition.row].substring(
          child.startPosition.column,
          child.endPosition.column
        ).trim();
        break;
      }
      // Python: look for 'def' or 'class' keyword's sibling
      if (child.type === 'def' || child.type === 'class') {
        var nextChild = node.child(i + 1);
        if (nextChild) {
          name = sourceLines[nextChild.startPosition.row].substring(
            nextChild.startPosition.column,
            nextChild.endPosition.column
          ).trim();
        }
        break;
      }
    }

    // 提取签名文本
    var sigLines = [];
    for (var row = startRow; row <= endRow; row++) {
      sigLines.push(sourceLines[row]);
      // 遇到函数体开始就停止
      if (sourceLines[row].includes('{') || sourceLines[row].includes(':')) break;
    }
    var signature = sigLines.join('\n').trim();

    return { name: name, signature: signature, line: startRow + 1 };
  }

  // 提取装饰器/注解
  function extractDecorators(node, sourceLines) {
    var decorators = [];
    if (node.type === 'decorated_definition') {
      for (var i = 0; i < node.childCount; i++) {
        var child = node.child(i);
        if (child.type === 'decorator') {
          var row = child.startPosition.row;
          decorators.push(sourceLines[row].trim());
        }
      }
    }
    return decorators;
  }

  // 主分析函数：解析代码，返回结构化摘要
  async function analyzeCode(filePath, sourceCode) {
    var lang = detectLanguage(filePath);
    if (!lang) {
      return null; // 不支持的语言
    }

    var success = await init();
    if (!success || !languages[lang]) {
      return null; // tree-sitter 不可用，回退
    }

    try {
      var parser = new Parser();
      parser.setLanguage(languages[lang]);

      var tree = parser.parse(sourceCode);
      if (!tree) return null;

      var sourceLines = sourceCode.split('\n');
      var patterns = NODE_PATTERNS[lang] || {};
      var result = {
        language: lang,
        file: filePath,
        imports: [],
        classes: [],
        functions: [],
        interfaces: [],
        types: [],
        structs: [],
        enums: [],
        traits: [],
        impls: [],
        exports: [],
        summary: ''
      };

      // 遍历 AST
      var cursor = tree.walk();
      var visited = {};

      function visitNode(node) {
        if (!node) return;
        var type = node.type;

        // 处理函数定义
        if (patterns.functions && patterns.functions.indexOf(type) >= 0) {
          // 如果是 decorated_definition，找里面的真正定义
          if (type === 'decorated_definition') {
            for (var i = 0; i < node.childCount; i++) {
              var child = node.child(i);
              if (patterns.functions.indexOf(child.type) >= 0) {
                var sig = extractSignature(child, sourceLines);
                var decs = extractDecorators(node, sourceLines);
                if (decs.length > 0) sig.decorators = decs;
                result.functions.push(sig);
              }
            }
          } else {
            result.functions.push(extractSignature(node, sourceLines));
          }
        }

        // 处理类定义
        if (patterns.classes && patterns.classes.indexOf(type) >= 0) {
          var classInfo = extractSignature(node, sourceLines);

          // 提取类中的方法
          classInfo.methods = [];
          for (var j = 0; j < node.childCount; j++) {
            var body = node.child(j);
            if (body) {
              // 递归查找方法
              var methodCursor = body.walk();
              var visitMethods = function(n) {
                if (!n) return;
                if (n.type === 'method_definition' || n.type === 'function_definition' ||
                    n.type === 'method_declaration' || n.type === 'function_declaration' ||
                    n.type === 'function_item') {
                  classInfo.methods.push(extractSignature(n, sourceLines));
                }
                for (var k = 0; k < n.childCount; k++) {
                  visitMethods(n.child(k));
                }
              };
              visitMethods(body);
            }
          }

          result.classes.push(classInfo);
        }

        // 处理接口
        if (patterns.interfaces && patterns.interfaces.indexOf(type) >= 0) {
          result.interfaces.push(extractSignature(node, sourceLines));
        }

        // 处理类型定义
        if (patterns.types && patterns.types.indexOf(type) >= 0) {
          result.types.push(extractSignature(node, sourceLines));
        }

        // 处理 Go struct
        if (patterns.structs && patterns.structs.indexOf(type) >= 0) {
          result.structs.push(extractSignature(node, sourceLines));
        }

        // 处理 Rust trait/impl
        if (patterns.traits && patterns.traits.indexOf(type) >= 0) {
          result.traits.push(extractSignature(node, sourceLines));
        }
        if (patterns.impls && patterns.impls.indexOf(type) >= 0) {
          result.impls.push(extractSignature(node, sourceLines));
        }

        // 处理导入
        if (patterns.imports && patterns.imports.indexOf(type) >= 0) {
          var row = node.startPosition.row;
          result.imports.push(sourceLines[row].trim());
        }

        // 递归子节点
        for (var c = 0; c < node.childCount; c++) {
          visitNode(node.child(c));
        }
      }

      visitNode(tree.rootNode);

      // 生成结构摘要文本
      result.summary = generateSummary(result);

      tree.delete();
      parser.delete();

      return result;
    } catch(e) {
      console.warn('[tree-sitter] Parse error for ' + filePath + ':', e.message);
      return null;
    }
  }

  // 生成人类可读的结构摘要
  function generateSummary(result) {
    var lines = [];

    if (result.imports.length > 0) {
      lines.push('Imports (' + result.imports.length + '):');
      result.imports.slice(0, 10).forEach(function(imp) {
        lines.push('  ' + imp);
      });
      if (result.imports.length > 10) lines.push('  ... +' + (result.imports.length - 10) + ' more');
      lines.push('');
    }

    if (result.classes.length > 0) {
      lines.push('Classes (' + result.classes.length + '):');
      result.classes.forEach(function(cls) {
        lines.push('  L' + cls.line + ': ' + cls.signature);
        if (cls.methods && cls.methods.length > 0) {
          lines.push('    Methods (' + cls.methods.length + '):');
          cls.methods.slice(0, 8).forEach(function(m) {
            lines.push('      L' + m.line + ': ' + m.signature);
          });
          if (cls.methods.length > 8) lines.push('      ... +' + (cls.methods.length - 8) + ' more');
        }
      });
      lines.push('');
    }

    if (result.functions.length > 0) {
      lines.push('Functions (' + result.functions.length + '):');
      result.functions.slice(0, 15).forEach(function(fn) {
        var decInfo = fn.decorators ? ' [' + fn.decorators.join(', ') + ']' : '';
        lines.push('  L' + fn.line + ': ' + fn.signature + decInfo);
      });
      if (result.functions.length > 15) lines.push('  ... +' + (result.functions.length - 15) + ' more');
      lines.push('');
    }

    if (result.interfaces.length > 0) {
      lines.push('Interfaces (' + result.interfaces.length + '):');
      result.interfaces.forEach(function(i) {
        lines.push('  L' + i.line + ': ' + i.signature);
      });
      lines.push('');
    }

    if (result.types.length > 0) {
      lines.push('Types (' + result.types.length + '):');
      result.types.slice(0, 10).forEach(function(t) {
        lines.push('  L' + t.line + ': ' + t.signature);
      });
      lines.push('');
    }

    if (result.structs.length > 0) {
      lines.push('Structs (' + result.structs.length + '):');
      result.structs.forEach(function(s) {
        lines.push('  L' + s.line + ': ' + s.signature);
      });
      lines.push('');
    }

    if (result.traits.length > 0) {
      lines.push('Traits (' + result.traits.length + '):');
      result.traits.forEach(function(t) {
        lines.push('  L' + t.line + ': ' + t.signature);
      });
      lines.push('');
    }

    if (result.impls.length > 0) {
      lines.push('Implementations (' + result.impls.length + '):');
      result.impls.forEach(function(i) {
        lines.push('  L' + i.line + ': ' + i.signature);
      });
      lines.push('');
    }

    return lines.join('\n');
  }

  // 检查是否可用
  function isAvailable() {
    return initialized && Object.keys(languages).length > 0;
  }

  // 获取支持的语言列表
  function getSupportedLanguages() {
    return Object.keys(languages);
  }

  // 导出
  global.TreeSitterAnalyzer = {
    init: init,
    analyzeCode: analyzeCode,
    isAvailable: isAvailable,
    getSupportedLanguages: getSupportedLanguages,
    detectLanguage: detectLanguage,
    generateSummary: generateSummary
  };

})(typeof window !== 'undefined' ? window : this);
