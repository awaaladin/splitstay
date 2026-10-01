/* Landing page motion. Vanilla JS, no libraries: reveal on scroll, word-by-word headline,
   cursor spotlight, magnetic buttons, the sticky story stage, and the looping hero demo. */
(function () {
  'use strict';
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------- split headline into words ---------- */
  $$('[data-split]').forEach(function (el) {
    var words = el.textContent.trim().split(/\s+/);
    el.setAttribute('aria-label', el.textContent.trim());
    el.innerHTML = words.map(function (w, i) {
      return '<span class="w" style="--i:' + i + '" aria-hidden="true">' + w + '</span>';
    }).join(' ');
    el.classList.add('words');
  });

  /* ---------- reveal on scroll (and after the boot screen has gone) ---------- */
  function observeReveals() {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
      });
    }, { threshold: 0.18, rootMargin: '0px 0px -6% 0px' });
    $$('.reveal, .words').forEach(function (el) { io.observe(el); });
  }
  document.addEventListener('cp:ready', observeReveals);

  /* ---------- count-up numbers ---------- */
  var countIO = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      countIO.unobserve(e.target);
      var el = e.target, to = parseFloat(el.getAttribute('data-count')), t0 = null;
      if (reduce) { el.textContent = to; return; }
      (function step(t) {
        if (t0 === null) t0 = t;
        var p = Math.min((t - t0) / 1400, 1), eased = 1 - Math.pow(1 - p, 4);
        el.textContent = Math.round(to * eased);
        if (p < 1) requestAnimationFrame(step);
      })(performance.now());
    });
  }, { threshold: 0.6 });
  $$('[data-count]').forEach(function (el) { countIO.observe(el); });

  /* ---------- cursor glow in dark bands, spotlight on cards ---------- */
  $$('.force-dark').forEach(function (sec) {
    sec.addEventListener('pointermove', function (e) {
      var r = sec.getBoundingClientRect();
      sec.style.setProperty('--hx', ((e.clientX - r.left) / r.width * 100) + '%');
      sec.style.setProperty('--hy', ((e.clientY - r.top) / r.height * 100) + '%');
    });
  });
  $$('[data-spot]').forEach(function (card) {
    card.addEventListener('pointermove', function (e) {
      var r = card.getBoundingClientRect();
      card.style.setProperty('--mx', (e.clientX - r.left) + 'px');
      card.style.setProperty('--my', (e.clientY - r.top) + 'px');
    });
  });

  /* ---------- magnetic buttons ---------- */
  if (!reduce) {
    $$('[data-magnetic]').forEach(function (btn) {
      btn.addEventListener('pointermove', function (e) {
        var r = btn.getBoundingClientRect();
        var x = (e.clientX - (r.left + r.width / 2)) * 0.18, y = (e.clientY - (r.top + r.height / 2)) * 0.28;
        btn.style.transform = 'translate(' + x + 'px,' + y + 'px)';
      });
      btn.addEventListener('pointerleave', function () { btn.style.transform = ''; });
    });
  }

  /* ---------- story: active chapter drives the sticky stage ---------- */
  var stage = $('#stage'), rail = $('#rail'), chapters = $$('.chapter');
  var typed = $('#typed-token'), typingTimer = null;
  function typeToken() {
    if (!typed) return;
    var text = typed.getAttribute('data-text'), i = 0;
    clearInterval(typingTimer);
    typed.textContent = ''; typed.classList.add('caret');
    if (reduce) { typed.textContent = text; typed.classList.remove('caret'); return; }
    typingTimer = setInterval(function () {
      typed.textContent = text.slice(0, ++i);
      if (i >= text.length) { clearInterval(typingTimer); setTimeout(function () { typed.classList.remove('caret'); }, 1200); }
    }, 70);
  }
  function setChapter(i) {
    chapters.forEach(function (c, n) { c.classList.toggle('active', n === i); });
    if (stage) stage.setAttribute('data-active', i);
    if (rail) rail.style.setProperty('--p', ((i + 1) / chapters.length * 100) + '%');
    if (i === 1) typeToken();
    if (i === 2) cycleMonths(true);
  }
  if (chapters.length) {
    var chIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) setChapter(parseInt(e.target.getAttribute('data-chapter'), 10));
      });
    }, { rootMargin: '-42% 0px -42% 0px' });
    chapters.forEach(function (c) { chIO.observe(c); });
    if (rail) rail.style.setProperty('--p', (100 / chapters.length) + '%');
  }

  /* share bars in the stage animate when their layer is shown */
  if (stage) {
    var bars = $$('.layer-2 .share-bar', stage);
    new MutationObserver(function () {
      var on = stage.getAttribute('data-active') === '2';
      bars.forEach(function (b) { b.classList.toggle('in', on); });
    }).observe(stage, { attributes: true, attributeFilter: ['data-active'] });
  }
  /* share bars in the feature cards animate when their card reveals (CSS: .reveal.in .share-bar) */

  var monthTimer = null;
  function cycleMonths(start) {
    var chips = $$('#months .month-chip'); if (!chips.length) return;
    clearInterval(monthTimer);
    if (!start || reduce) return;
    var i = 0;
    monthTimer = setInterval(function () {
      i = (i + 1) % chips.length;
      chips.forEach(function (c, n) { c.classList.toggle('on', n === i); });
    }, 1500);
  }

  /* ---------- guide: highlight the table-of-contents entry for the part being read ---------- */
  var tocLinks = $$('#guide-toc .toc-link'), parts = $$('.g-part');
  if (tocLinks.length && parts.length) {
    var tocIO = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        tocLinks.forEach(function (a) { a.classList.toggle('on', a.getAttribute('href') === '#' + e.target.id); });
      });
    }, { rootMargin: '-20% 0px -65% 0px' });
    parts.forEach(function (p) { tocIO.observe(p); });
  }

  /* ---------- hero demo: a month of rent in 14 seconds, on a loop ---------- */
  var members = [
    { share: 133333.34, who: 'Ada Okafor' },
    { share: 200000.00, who: 'Tunde Bello' },
    { share: 133333.33, who: 'Chioma Eze' },
    { share: 133333.33, who: 'Ibrahim Musa' }
  ];
  var TARGET = 600000;
  var liquid = $('#h-liquid'), fundedEl = $('#h-funded'), pctEl = $('#h-pct'), statusEl = $('#h-status');
  var ledger = $('#h-ledger'), badge = $('#h-badge'), badgeText = $('#h-badge-text');
  var sent = $('#h-sent'), tokenCard = $('#h-token');
  var rows = $$('#h-members li');
  var timers = [], shown = 0;

  function fmt(n) { return '₦' + n.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
  function tween(from, to, ms, cb) {
    if (reduce) { cb(to); return; }
    var t0 = null;
    (function step(t) {
      if (t0 === null) t0 = t;
      var p = Math.min((t - t0) / ms, 1), e = 1 - Math.pow(1 - p, 3);
      cb(from + (to - from) * e);
      if (p < 1) requestAnimationFrame(step);
    })(performance.now());
  }
  function setLevel(total) {
    var pct = Math.min(total / TARGET * 100, 100);
    liquid.style.transform = 'translateY(' + (100 - pct) + '%)';
    tween(shown, total, 1100, function (v) { fundedEl.textContent = fmt(v); });
    shown = total;
    pctEl.textContent = pct.toFixed(pct === 100 ? 0 : 1) + '%';
  }
  function reset() {
    liquid.style.transform = 'translateY(100%)';
    fundedEl.textContent = fmt(0); pctEl.textContent = '0%'; shown = 0;
    statusEl.textContent = 'Waiting for the first payment…';
    ledger.innerHTML = '';
    badge.className = 'badge-neutral'; badgeText.textContent = 'Open';
    rows.forEach(function (r) {
      var b = r.querySelector('.h-state'); b.className = 'badge-neutral h-state'; b.innerHTML = '<span class="dot"></span>Not yet paid';
    });
    sent.classList.remove('on'); tokenCard.classList.remove('on');
  }
  function pay(i, total) {
    var b = rows[i].querySelector('.h-state');
    b.className = 'badge-ok h-state state-flip'; b.innerHTML = '<span class="dot"></span>Paid';
    var li = document.createElement('li');
    li.className = 'flex items-center justify-between is-new';
    li.innerHTML = '<span><span class="text-ok">+</span> ' + members[i].who + ' paid</span><span class="amount">' + fmt(members[i].share) + '</span>';
    ledger.insertBefore(li, ledger.firstChild);
    while (ledger.children.length > 1) ledger.removeChild(ledger.lastChild);
    setLevel(total);
    statusEl.textContent = (i < 3 ? (3 - i) + ' still to pay' : 'Target reached');
  }
  function at(ms, fn) { timers.push(setTimeout(fn, ms)); }
  function loop() {
    reset();
    var running = 0;
    var T = [1300, 3600, 5700, 7800];
    members.forEach(function (m, i) { running += m.share; var total = running; at(T[i], function () { pay(i, total); }); });
    at(8900, function () {
      badge.className = 'badge-ok'; badgeText.textContent = 'Paid out';
      tokenCard.classList.add('on');
      statusEl.textContent = 'Payment sent to the landlord';
    });
    at(9700, function () { sent.classList.add('on'); });
    at(15200, function () { sent.classList.remove('on'); tokenCard.classList.remove('on'); });
    at(15900, loop);
  }
  function staticFinal() {
    var total = 0; members.forEach(function (m, i) { total += m.share; });
    rows.forEach(function (r, i) { var b = r.querySelector('.h-state'); b.className = 'badge-ok h-state'; b.innerHTML = '<span class="dot"></span>Paid'; });
    liquid.style.transform = 'translateY(0%)'; fundedEl.textContent = fmt(total); pctEl.textContent = '100%';
    statusEl.textContent = 'Payment sent to the landlord'; badge.className = 'badge-ok'; badgeText.textContent = 'Paid out';
    sent.classList.add('on');
  }

  if (liquid) {
    document.addEventListener('cp:ready', function () {
      if (reduce) { staticFinal(); return; }
      var visible = true;
      new IntersectionObserver(function (e) { visible = e[0].isIntersecting; }).observe($('#hero'));
      loop();
      // pause the cycle while the hero is off-screen or the tab is hidden, resume from the start
      document.addEventListener('visibilitychange', function () {
        timers.forEach(clearTimeout); timers = [];
        if (!document.hidden && visible) loop();
      });
    });
  }
})();
