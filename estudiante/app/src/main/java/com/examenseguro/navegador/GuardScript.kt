package com.examenseguro.navegador

/** JavaScript que se inyecta en cada página del examen antes de que cargue. */
object GuardScript {
    val SOURCE = """
        (function () {
          if (window.__examenSeguro) return;
          window.__examenSeguro = { version: '1.0' };
          var isField = function (el) {
            return el && (el.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(el.tagName));
          };
          var block = function (e) { e.preventDefault(); e.stopImmediatePropagation(); return false; };
          ['copy', 'cut', 'paste', 'contextmenu', 'dragstart', 'drop', 'beforeprint'].forEach(function (t) {
            document.addEventListener(t, block, true);
          });
          document.addEventListener('selectstart', function (e) {
            if (!isField(e.target)) block(e);
          }, true);
          document.addEventListener('keydown', function (e) {
            if ((e.ctrlKey || e.metaKey) && /^[cvxaps]$/i.test(e.key)) block(e);
          }, true);
          window.print = function () {};
          var css = '*:not(input):not(textarea):not([contenteditable]){' +
            '-webkit-user-select:none!important;user-select:none!important;' +
            '-webkit-touch-callout:none!important;}';
          var addStyle = function () {
            var s = document.createElement('style');
            s.textContent = css;
            (document.head || document.documentElement).appendChild(s);
          };
          if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', addStyle);
          else addStyle();
        })();
    """.trimIndent()
}
