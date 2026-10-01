/* SplitStay front-end behaviour. Alpine handles UI state; this file holds the few things that need
   real timing control: the boot screen, the pot fill, number count-ups and the delayed busy state. */
(function () {
  'use strict';

  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ---------------------------------------------------------------- theme */
  function applyTheme(dark) {
    document.documentElement.classList.toggle('dark', dark);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', dark ? '#080f22' : '#102a56');
  }

  document.addEventListener('alpine:init', function () {
    Alpine.data('themeToggle', function () {
      return {
        dark: document.documentElement.classList.contains('dark'),
        toggle: function () {
          this.dark = !this.dark;
          applyTheme(this.dark);
          try { localStorage.setItem('cp-theme', this.dark ? 'dark' : 'light'); } catch (e) {}
        },
      };
    });

    /* Group create/edit form: purpose presets, payout type, dynamic member rows, live split preview. */
    Alpine.data('groupForm', function (cfg) {
      return {
        purpose: cfg.purpose || 'rent',
        payoutType: cfg.payoutType || 'bank_transfer',
        recurring: !!cfg.recurring,
        target: cfg.target || '',
        members: cfg.members && cfg.members.length ? cfg.members : [],
        fee: cfg.fee,
        editing: !!cfg.editing,
        setPurpose: function (p) {
          this.purpose = p;
          if (this.editing) return;
          this.payoutType = p === 'electricity' ? 'bill_payment' : 'bank_transfer';
        },
        addMember: function () { this.members.push({ identifier: '', share: '' }); },
        removeMember: function (i) { this.members.splice(i, 1); },
        get targetNumber() { var n = parseFloat(String(this.target).replace(/,/g, '')); return isNaN(n) ? 0 : n; },
        get customTotal() {
          return this.members.reduce(function (t, m) { var n = parseFloat(String(m.share).replace(/,/g, '')); return t + (isNaN(n) ? 0 : n); }, 0);
        },
        get headcount() { return 1 + this.members.filter(function (m) { return m.identifier.trim(); }).length; },
        get customCount() { return this.members.filter(function (m) { return m.identifier.trim() && String(m.share).trim(); }).length; },
        get equalShare() {
          var others = this.headcount - this.customCount;
          if (others <= 0) return 0;
          return Math.max(this.targetNumber - this.customTotal, 0) / others;
        },
        get feeAmount() {
          if (!this.fee) return 0;
          return this.fee.type === 'percent' ? this.targetNumber * this.fee.percent / 100 : this.fee.flat;
        },
        money: function (n) { return '₦' + Number(n).toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); },
      };
    });
  });

  /* Follow the system preference live, but only while the user has not chosen explicitly. */
  try {
    var mq = window.matchMedia('(prefers-color-scheme: dark)');
    var onSystem = function (e) { if (!localStorage.getItem('cp-theme')) applyTheme(e.matches); };
    if (mq.addEventListener) mq.addEventListener('change', onSystem);
  } catch (e) {}

  /* ---------------------------------------------------------------- boot screen */
  var BOOT_MIN_MS = 950;
  var started = performance.now();
  var ready = false;

  function announceReady() {
    if (ready) return;
    ready = true;
    document.dispatchEvent(new CustomEvent('cp:ready'));
  }

  function finishBoot() {
    var boot = document.getElementById('boot');
    try { sessionStorage.setItem('cp-booted', '1'); } catch (e) {}
    if (!boot || document.documentElement.classList.contains('booted')) { announceReady(); return; }
    var wait = reduceMotion ? 0 : Math.max(0, BOOT_MIN_MS - (performance.now() - started));
    setTimeout(function () {
      boot.classList.add('boot-out');
      announceReady();
      setTimeout(function () { boot.remove(); }, 420);
    }, wait);
  }

  if (document.readyState === 'complete') finishBoot();
  else window.addEventListener('load', finishBoot);

  /* ---------------------------------------------------------------- pot + bars */
  function fillPots(root) {
    root.querySelectorAll('[data-pot-liquid][data-translate]').forEach(function (el) {
      var target = el.getAttribute('data-translate');
      el.removeAttribute('data-translate');
      // two frames so the browser paints the empty state first; the transition then does the fill
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { el.style.transform = 'translateY(' + target + '%)'; });
      });
    });
    root.querySelectorAll('.bar > i[data-fill]').forEach(function (el) {
      var w = el.getAttribute('data-fill');
      el.removeAttribute('data-fill');
      requestAnimationFrame(function () { requestAnimationFrame(function () { el.style.width = w + '%'; }); });
    });
  }

  /* ---------------------------------------------------------------- count-up */
  var lastValues = {};
  function format(n, places) {
    return '₦' + n.toLocaleString('en-NG', { minimumFractionDigits: places, maximumFractionDigits: places });
  }
  function countUp(el, from, to) {
    var places = parseInt(el.getAttribute('data-places') || '2', 10);
    if (reduceMotion || from === to) { el.textContent = format(to, places); return; }
    var duration = 1300, t0 = null;
    function step(t) {
      if (t0 === null) t0 = t;
      var p = Math.min((t - t0) / duration, 1);
      var eased = 1 - Math.pow(1 - p, 3);
      el.textContent = format(from + (to - from) * eased, places);
      if (p < 1) requestAnimationFrame(step); else el.textContent = format(to, places);
    }
    requestAnimationFrame(step);
  }
  function runCounts(root, initial) {
    root.querySelectorAll('[data-count-to]').forEach(function (el) {
      var to = parseFloat(el.getAttribute('data-count-to'));
      var key = el.getAttribute('data-count-key') || el.id;
      var from = initial ? 0 : (key in lastValues ? lastValues[key] : to);
      if (key) lastValues[key] = to;
      countUp(el, from, to);
    });
  }

  document.addEventListener('cp:ready', function () {
    fillPots(document);
    runCounts(document, true);
  });

  /* ---------------------------------------------------------------- live updates (htmx) */
  var seenRows = null;
  function markNewRows(root, initial) {
    var rows = root.querySelectorAll('[data-entry]');
    if (seenRows === null || initial) {
      seenRows = {};
      rows.forEach(function (r) { seenRows[r.getAttribute('data-entry')] = 1; });
      return;
    }
    rows.forEach(function (r) {
      var id = r.getAttribute('data-entry');
      if (!seenRows[id]) { seenRows[id] = 1; if (!reduceMotion) r.classList.add('is-new'); }
    });
  }
  document.addEventListener('cp:ready', function () { markNewRows(document, true); });

  var lastPercent = null;
  document.addEventListener('htmx:afterSettle', onSettle);
  function onSettle() {
    var root = document;
    var pot = document.getElementById('pot');
    if (pot) {
      var pct = parseFloat(pot.getAttribute('data-percent'));
      if (lastPercent !== null && pct > lastPercent) {
        pot.classList.add('rising');
        clearTimeout(pot.__riseTimer);
        pot.__riseTimer = setTimeout(function () { pot.classList.remove('rising'); }, 2400);
      }
      lastPercent = pct;
    }
    runCounts(root, false);
    markNewRows(root, false);
  }
  document.addEventListener('cp:ready', function () {
    var pot = document.getElementById('pot');
    if (pot) lastPercent = parseFloat(pot.getAttribute('data-percent'));
  });

  /* ---------------------------------------------------------------- delayed busy state */
  var busy, busyTimer, inflight = 0;
  function showBusyLater() {
    inflight++;
    if (busyTimer) return;
    busyTimer = setTimeout(function () {
      busy = busy || document.getElementById('busy');
      if (busy && inflight > 0) busy.classList.add('on');
    }, 550);
  }
  function hideBusy() {
    inflight = Math.max(0, inflight - 1);
    if (inflight > 0) return;
    clearTimeout(busyTimer); busyTimer = null;
    busy = busy || document.getElementById('busy');
    if (busy) busy.classList.remove('on');
  }
  document.addEventListener('htmx:beforeRequest', function (e) {
    var el = e.detail.elt;
    if (el && el.closest && el.closest('[data-quiet]')) { e.detail.__quiet = true; return; }
    showBusyLater();
  });
  document.addEventListener('htmx:afterRequest', function (e) {
    var el = e.detail.elt;
    if (el && el.closest && el.closest('[data-quiet]')) return;
    hideBusy();
  });
  /* Ordinary form posts (pay, payout, sign in): show the branded state only if the server is slow. */
  document.addEventListener('submit', function (e) {
    var form = e.target;
    if (form && form.matches && form.matches('form[data-busy]')) showBusyLater();
  });
  window.addEventListener('pageshow', function (e) { if (e.persisted) { inflight = 0; hideBusy(); } });
})();
