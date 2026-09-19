/* Zonely front end. Reads the team out of the DOM, asks the server to score
   every slot, and paints the result. No framework, no build step. */

const $  = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

const membersEl = $('#members');
const slotsEl   = $('#slots');
const stripEl   = $('#heatstrip');
const statusEl  = $('#status');
const tmpl      = $('#member-template');

const DEFAULTS = { work_start: 9, work_end: 17, sleep_start: 23, sleep_end: 7, burden: 0 };

/* ---------- reading & writing the team ---------- */

function addMember(data = {}) {
  if ($$('.member').length >= 12) return;
  const node = tmpl.content.firstElementChild.cloneNode(true);
  const m = { ...DEFAULTS, name: '', tz: '', ...data };

  $('.m-name', node).value        = m.name;
  $('.m-tz', node).value          = m.tz;
  $('.m-start', node).value       = m.work_start;
  $('.m-end', node).value         = m.work_end;
  $('.m-sleep-start', node).value = m.sleep_start;
  $('.m-sleep-end', node).value   = m.sleep_end;
  $('.m-burden', node).textContent = Math.round(m.burden);
  node.dataset.burden = m.burden;

  $('.remove', node).addEventListener('click', () => { node.remove(); refresh(); });
  $('.reset-burden', node).addEventListener('click', () => {
    node.dataset.burden = 0;
    $('.m-burden', node).textContent = '0';
    refresh();
  });
  membersEl.appendChild(node);
}

function readMembers() {
  return $$('.member', membersEl).map(node => ({
    name:        $('.m-name', node).value.trim(),
    tz:          $('.m-tz', node).value.trim(),
    work_start:  parseFloat($('.m-start', node).value),
    work_end:    parseFloat($('.m-end', node).value),
    sleep_start: parseFloat($('.m-sleep-start', node).value),
    sleep_end:   parseFloat($('.m-sleep-end', node).value),
    burden:      parseFloat(node.dataset.burden || 0),
  })).filter(m => m.tz);
}

/* ---------- rendering ---------- */

function bandFor(pain) {
  if (pain >= 100) return 'sleep';
  if (pain === 0)  return 'work';
  return pain < 50 ? 'edge' : 'rough';
}

function renderSlots(slots, duration) {
  slotsEl.innerHTML = '';
  if (!slots.length) {
    slotsEl.innerHTML = '<p class="empty">Add a teammate to see suggestions.</p>';
    return;
  }

  slots.forEach((slot, i) => {
    const el = document.createElement('div');
    el.className = 'slot' + (i === 0 ? ' best' : '') + (slot.everyone_awake ? '' : ' nobody-awake');

    const people = slot.members.map(p => {
      const off = p.day_offset === 0 ? ''
        : `<span class="plus">${p.day_offset > 0 ? '+' : '−'}${Math.abs(p.day_offset)}d</span>`;
      return `<span class="person ${bandFor(p.pain)}">
                <b>${escape(p.name)}</b><time>${p.local_label}</time>${off}
              </span>`;
    }).join('');

    const verdict = slot.worst_pain >= 100
      ? '<span class="badge warn">wakes someone</span>'
      : slot.worst_pain === 0
        ? '<span class="badge good">painless</span>'
        : `<span class="badge">worst ${Math.round(slot.worst_pain)}</span>`;

    el.innerHTML = `
      <div class="slot-time">${slot.utc_label}<small>UTC</small></div>
      <div class="slot-people">${people}</div>
      <div class="slot-meta">
        ${verdict}
        <span class="badge">fairness ${slot.fair_score}</span>
        <div class="slot-actions">
          <button type="button" class="btn btn-tiny log">Log it</button>
          <a class="btn btn-tiny" href="/ics?start=${encodeURIComponent(slot.start_utc)}&m=${duration}">.ics</a>
        </div>
      </div>`;

    $('.log', el).addEventListener('click', () => logMeeting(slot));
    slotsEl.appendChild(el);
  });
}

function renderHeatstrip(rows) {
  stripEl.innerHTML = '';
  if (!rows.length) return;

  rows.forEach(row => {
    const cells = row.cells.map(c =>
      `<div class="cell ${c.band}" title="${c.utc_hour}:00 UTC — ${escape(row.name)} ${c.local_label} (pain ${c.pain})"></div>`
    ).join('');
    const el = document.createElement('div');
    el.className = 'strip-row';
    el.innerHTML = `
      <div class="strip-name">
        <b>${escape(row.name)}</b>
        <span>${row.utc_offset} · burden ${row.burden}</span>
      </div>
      <div class="strip-cells">${cells}</div>`;
    stripEl.appendChild(el);
  });

  const axis = document.createElement('div');
  axis.className = 'strip-axis';
  const ticks = Array.from({ length: 24 }, (_, h) => `<span>${h % 3 === 0 ? h : ''}</span>`).join('');
  axis.innerHTML = `<div></div><div class="ticks">${ticks}</div>`;
  stripEl.appendChild(axis);
}

function escape(s) {
  return String(s).replace(/[&<>"']/g, ch =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));
}

/* ---------- the rotation: logging a meeting shifts future suggestions ---------- */

function logMeeting(slot) {
  const painBy = Object.fromEntries(slot.members.map(p => [p.name, p.pain]));
  $$('.member', membersEl).forEach(node => {
    const name = $('.m-name', node).value.trim();
    const added = painBy[name];
    if (added === undefined) return;
    const next = parseFloat(node.dataset.burden || 0) + added;
    node.dataset.burden = next;
    $('.m-burden', node).textContent = Math.round(next);
  });
  statusEl.textContent = `Logged ${slot.utc_label} UTC — future plans will rotate away from whoever took the hit.`;
  refresh({ keepStatus: true });
}

/* ---------- talking to the server ---------- */

let pending;

async function refresh({ keepStatus = false } = {}) {
  const members = readMembers();
  const day = $('#day').value;
  const duration = parseInt($('#duration').value, 10);

  if (!keepStatus) statusEl.textContent = '';
  if (!members.length) {
    renderSlots([], duration);
    renderHeatstrip([]);
    return;
  }

  clearTimeout(pending);
  pending = setTimeout(async () => {
    try {
      const res = await fetch('/api/plan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ members, day, duration }),
      });
      const data = await res.json();
      renderSlots(data.slots || [], duration);
      renderHeatstrip(data.heatstrip || []);
      updateShare(data.token, day, duration);
    } catch (err) {
      statusEl.textContent = 'Could not reach the server.';
    }
  }, 180);
}

function updateShare(token, day, duration) {
  const url = `${location.origin}/?t=${token}&d=${day}&m=${duration}`;
  $('#share-url').value = url;
  history.replaceState(null, '', `/?t=${token}&d=${day}&m=${duration}`);
}

/* ---------- wiring ---------- */

$('#add-member').addEventListener('click', () => { addMember(); refresh(); });
$('#day').addEventListener('change', () => refresh());
$('#duration').addEventListener('change', () => refresh());
membersEl.addEventListener('input', () => refresh());

$$('.chip').forEach(chip => chip.addEventListener('click', () => {
  addMember({ name: chip.dataset.label, tz: chip.dataset.tz });
  refresh();
}));

$('#copy-link').addEventListener('click', async () => {
  const btn = $('#copy-link');
  try {
    await navigator.clipboard.writeText($('#share-url').value);
    btn.textContent = 'Copied';
  } catch {
    $('#share-url').select();
    btn.textContent = 'Press ⌘C';
  }
  setTimeout(() => (btn.textContent = 'Copy'), 1600);
});

(window.ZONELY.members || []).forEach(addMember);
if (!$$('.member').length) addMember({ name: 'Me', tz: Intl.DateTimeFormat().resolvedOptions().timeZone });
refresh();
