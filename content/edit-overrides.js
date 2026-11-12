/* ATTACHÉ manual text overrides (shared by the public pages and /edit/).
   Pages: apply_overrides.py inlines this file plus a JSON block (#edit-ov) holding the page's sections and
   active overrides. On load the page applies the baked overrides, then re-reads content/overrides.json so a
   save from /edit/ shows up as soon as Pages deploys. Add ?ov=off to any page URL to see the pipeline text. */
(function () {
  var OV = window.AttacheOV = window.AttacheOV || {};
  var esc = function (s) { return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;'); };
  var norm = function (s) { return String(s || '').replace(/\s+/g, ' ').trim(); };

  OV.active = function (o, now) {
    if (!o || typeof o.text !== 'string' || !o.text.trim()) return false;
    if (!o.expires) return true;
    var t = Date.parse(o.expires);
    return isNaN(t) ? false : t > (now || Date.now());
  };

  function pick(list, step) {
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var el = list[i];
      if (step.has) {
        var h = el.querySelector(step.has.sel);
        if (!h || norm(h.textContent).toUpperCase().indexOf(norm(step.has.starts).toUpperCase()) !== 0) continue;
      }
      if (step.bare) { // first non-blank child node must be text (no leading label)
        var n = el.firstChild;
        while (n && n.nodeType === 3 && !n.textContent.trim()) n = n.nextSibling;
        if (!n || n.nodeType !== 3) continue;
      }
      out.push(el);
    }
    return out;
  }

  // steps: [{sel, has:{sel,starts}, bare, nth}] applied in order from the document
  OV.locate = function (doc, steps) {
    var cur = [doc];
    for (var s = 0; s < steps.length; s++) {
      var st = steps[s], found = [];
      for (var c = 0; c < cur.length; c++) {
        var q;
        try { q = cur[c].querySelectorAll(st.sel); } catch (x) { return null; }
        found = found.concat(pick(Array.prototype.slice.call(q), st));
      }
      if (!found.length) return null;
      cur = [found[st.nth || 0]];
      if (!cur[0]) return null;
    }
    return cur[0] === doc ? null : cur[0];
  };

  function inline(s, br) {
    var h = esc(s).replace(/\*\*([^*\n]+)\*\*/g, '<b>$1</b>');
    return br ? h.replace(/\r?\n/g, '<br>') : h.replace(/\s*\r?\n\s*/g, ' ');
  }
  var lines = function (t) { return String(t).split(/\r?\n/).map(function (l) { return l.replace(/^\s*(?:[-•]|\d+[.)])\s+/, '').trim(); }).filter(Boolean); };

  OV.stamp = function (iso) {
    var d = new Date(iso);
    if (isNaN(d)) return '';
    try {
      return 'edited ' + new Intl.DateTimeFormat('en-US', { timeZone: 'America/Los_Angeles', weekday: 'short', month: 'numeric', day: 'numeric', hour: 'numeric', minute: '2-digit' }).format(d).replace(/,/g, '') + ' PT';
    } catch (x) { return 'edited'; }
  };

  // Body HTML for a section (label kept separately by apply).
  OV.render = function (sec, o) {
    var st = sec.stamp === false ? '' : OV.stamp(o.set_at);
    var stS = '<span class="ov-st" style="color:#8a8470;font-size:11px;font-weight:400;margin-left:6px">· ' + esc(st) + '</span>';
    if (sec.mode === 'list' || sec.mode === 'numbered') {
      var L = lines(o.text), h = '<ul>';
      for (var i = 0; i < L.length; i++) {
        h += sec.mode === 'numbered'
          ? '<li class="nb"><span class="n">' + (i + 1) + '</span><span class="vv">' + inline(L[i]) + '</span></li>'
          : '<li><span class="vv">' + inline(L[i]) + '</span></li>';
      }
      return h + '</ul>' + (st ? '<div class="ov-st" style="color:#8a8470;font-size:11px">' + esc(st) + '</div>' : '');
    }
    return inline(o.text.trim(), !sec.inline) + (st ? stS : '');
  };

  function labelOf(el, sec) {
    if (!sec.keep_label) return null;
    var f = el.firstElementChild;
    return f || null;
  }

  // Current pipeline text of a section (what /edit/ pre-fills when nothing is locked).
  OV.text = function (el, sec) {
    var lab = labelOf(el, sec), kids = Array.prototype.slice.call(el.childNodes), out = [];
    if (sec.mode === 'list' || sec.mode === 'numbered') {
      kids.forEach(function (k) {
        if (k === lab || k.nodeType !== 1) return;
        if (/^(UL|OL)$/.test(k.tagName)) {
          Array.prototype.forEach.call(k.querySelectorAll(':scope > li'), function (li) {
            var v = li.querySelector('.vv'); out.push(norm((v || li).textContent));
          });
        } else if (!k.classList.contains('ov-st')) out.push(norm(k.textContent));
      });
      return lines(out.join('\n')).join('\n');
    }
    kids.forEach(function (k) {
      if (k === lab) return;
      if (k.nodeType === 1 && k.classList.contains('ov-st')) return;
      if (k.nodeType === 1 && k.tagName === 'BR') { out.push('\n'); return; }
      out.push(k.textContent);
    });
    return out.join('').replace(/[ \t]+/g, ' ').replace(/ *\n */g, '\n').trim();
  };

  OV.setBody = function (el, sec, html) {
    var lab = labelOf(el, sec);
    if (!lab) { el.innerHTML = html; return; }
    while (lab.nextSibling) el.removeChild(lab.nextSibling);
    el.insertAdjacentHTML('beforeend', ' ' + html);
  };

  // ---- page runtime ----
  var state = null, applied = {};
  function applyAll() {
    if (!state) return;
    var secs = state.sections || [], ovs = state.overrides || {}, now = Date.now();
    for (var i = 0; i < secs.length; i++) {
      var sec = secs[i], o = ovs[sec.id], on = OV.active(o, now);
      var el = OV.locate(document, sec.steps);
      if (!el) continue;
      if (on) {
        var html = OV.render(sec, o);
        if (el.__ovh === el.innerHTML && el.__ovk === html) continue;
        if (el.__ovo === undefined) el.__ovo = el.innerHTML;
        OV.setBody(el, sec, html);
        el.__ovh = el.innerHTML; el.__ovk = html; el.setAttribute('data-ov', sec.id);
        applied[sec.id] = 1;
      } else if (el.__ovo !== undefined) { // released or expired: put the pipeline text back
        el.innerHTML = el.__ovo; delete el.__ovo; delete el.__ovh; delete el.__ovk; el.removeAttribute('data-ov');
        delete applied[sec.id];
      }
    }
  }
  OV.applied = function () { return Object.keys(applied); };

  OV.boot = function () {
    var b = document.getElementById('edit-ov');
    if (!b || /(?:^|[?&])ov=off(?:&|$)/.test(location.search)) return;
    try { state = JSON.parse(b.textContent); } catch (x) { return; }
    var go = function () {
      applyAll();
      var dyn = (state.sections || []).some(function (s) { return s.dynamic; });
      if (dyn && window.MutationObserver) {
        var q = 0;
        new MutationObserver(function () { if (q) return; q = 1; setTimeout(function () { q = 0; applyAll(); }, 30); })
          .observe(document.body, { childList: true, subtree: true });
      }
      if (location.protocol === 'http:' || location.protocol === 'https:') {
        try {
          fetch((state.base || '../') + 'content/overrides.json?t=' + Math.floor(Date.now() / 30000), { cache: 'no-store' })
            .then(function (r) { return r.ok ? r.json() : null; })
            .then(function (j) { if (j && j.overrides) { state.overrides = j.overrides; applyAll(); } })
            .catch(function () {});
        } catch (x) {}
      }
    };
    document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', go) : go();
    window.addEventListener('load', applyAll);
  };
})();
