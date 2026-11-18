// SPDX-License-Identifier: MIT
// Environment writes are explicit. All output readbacks come from real drivers.
const byId = (id) => document.getElementById(id);
const views = [];
const inputChecks = [];
const inputReadbacks = [];
const relayReadbacks = [];
const deviceViews = new Map();
let latest = null;
let writing = false;
let reading = null;
let generation = 0;
let timer = null;
let stopped = false;
let lcdClient = null;
let lcdRenderer = null;
let lcdGeneration = 0;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function message(node, text, error = false) {
  node.textContent = text;
  node.classList.toggle('error', error);
}

function showError(node, text) {
  node.textContent = text;
  node.hidden = !text;
}

function hex(value) {
  return typeof value === 'number' ? `0x${value.toString(16).padStart(4, '0')}` : 'unavailable';
}

function updateButtons() {
  for (const view of views) {
    for (const button of view.form.querySelectorAll('button')) button.disabled = writing || !latest;
  }
}

function createView(form, status, path, payload, sync) {
  const view = {form, status, path, payload, sync, dirty: false, saving: false, version: 0};
  const changed = () => {
    view.dirty = true;
    view.version += 1;
    message(status, 'Unsaved edits — not applied.');
  };
  form.addEventListener('input', changed);
  form.addEventListener('change', changed);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!latest || writing || !form.reportValidity()) return;
    let body;
    try {
      body = payload();
    } catch (error) {
      message(status, error.message, true);
      return;
    }
    save(view, body);
  });
  form.querySelector('[data-discard]').addEventListener('click', () => {
    if (!latest || writing) return;
    view.version += 1;
    view.dirty = false;
    sync(latest);
    message(status, 'Edits discarded; showing the latest applied environment.');
  });
  views.push(view);
  return view;
}

function registerValue(id) {
  const value = Number(byId(id).value);
  if (!Number.isInteger(value) || value < 0 || value > 65535 || byId(id).value.trim() === '') {
    throw new Error('Configuration and polarity must be integers from 0 to 65535.');
  }
  return value;
}

for (let channel = 1; channel <= 16; channel += 1) {
  const label = element('label', undefined, 'check channel');
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.id = `input-${channel}`;
  checkbox.name = `input-${channel}`;
  label.htmlFor = checkbox.id;
  label.append(checkbox, document.createTextNode(`Input ${channel}`));
  byId('input-controls').append(label);
  inputChecks.push(checkbox);
  const inputReadback = element('div', `Input ${channel}: unknown`, 'channel');
  const relayReadback = element('div', `Relay ${channel}: unknown`, 'channel');
  byId('decoded-inputs').append(inputReadback);
  byId('decoded-relays').append(relayReadback);
  inputReadbacks.push(inputReadback);
  relayReadbacks.push(relayReadback);
}

createView(byId('inputs-form'), byId('inputs-status'), '/sim/api/inputs', () => ({
  active: inputChecks.map((checkbox) => checkbox.checked),
  config: registerValue('input-config'),
  polarity: registerValue('input-polarity'),
}), (snapshot) => {
  inputChecks.forEach((checkbox, index) => { checkbox.checked = snapshot.inputs.active[index]; });
  byId('input-config').value = snapshot.inputs.config;
  byId('input-polarity').value = snapshot.inputs.polarity;
});

createView(byId('rtc-form'), byId('rtc-status'), '/sim/api/rtc', () => ({
  osf: byId('rtc-osf').checked,
}), (snapshot) => { byId('rtc-osf').checked = snapshot.devices.rtc.osf; });

for (const [device, title] of [
  ['relays', 'Relay expander · PCF8575'],
  ['inputs', 'Input expander · XL9535'],
  ['rtc', 'Clock · DS3231'],
  ['lcd', 'LCD · ST7789'],
]) {
  const form = element('form', undefined, 'device-card');
  form.id = `device-${device}-form`;
  form.append(element('h3', title));
  const actual = element('p', 'Applied state: unknown', 'muted');
  const label = element('label', undefined, 'check');
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  checkbox.id = `device-${device}-online`;
  checkbox.name = 'online';
  label.htmlFor = checkbox.id;
  label.append(checkbox, document.createTextNode(`${title.split(' · ')[0]} online`));
  const actions = element('div', undefined, 'actions');
  const apply = element('button', 'Apply device fault');
  apply.type = 'submit';
  const discard = element('button', 'Discard', 'secondary');
  discard.type = 'button';
  discard.dataset.discard = '';
  actions.append(apply, discard);
  const status = element('p', 'Waiting for the first snapshot.', 'form-status');
  status.id = `device-${device}-status`;
  status.setAttribute('role', 'status');
  form.append(actual, label, actions, status);
  byId('device-controls').append(form);
  createView(form, status, `/sim/api/devices/${device}`, () => ({online: checkbox.checked}),
    (snapshot) => { checkbox.checked = snapshot.devices[device].online; });
  deviceViews.set(device, {actual});
}

async function request(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', ...options});
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`HTTP ${response.status}: server did not return JSON.`);
  }
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${data.error?.message || response.statusText}`);
  return data;
}

// Only one state GET at a time. Ignore snapshots started before a write.
async function poll() {
  if (stopped || reading) return;
  clearTimeout(timer);
  if (writing) {
    timer = setTimeout(poll, 1000);
    return;
  }
  const controller = new AbortController();
  reading = controller;
  const started = generation;
  const deadline = setTimeout(() => controller.abort(), 10000);
  try {
    const snapshot = await request('/sim/api/state', {signal: controller.signal});
    if (!stopped && started === generation) {
      render(snapshot);
      showError(byId('network-error'), '');
      message(byId('connection-status'), 'Connected · actual driver reads refreshed about once per second.');
    }
  } catch (error) {
    if (!stopped && started === generation) {
      showError(byId('network-error'), `Refresh failed: ${error.message} Readbacks may be stale; staged edits are preserved.`);
      message(byId('connection-status'), 'Disconnected or stale — waiting for the next read.');
    }
  } finally {
    clearTimeout(deadline);
    reading = null;
    if (!stopped) timer = setTimeout(poll, 1000);
  }
}

// Never retry a POST: even a lost response can mean the operation was applied.
async function save(view, payload) {
  if (writing || stopped) return;
  const submittedVersion = view.version;
  writing = true;
  view.saving = true;
  generation += 1;
  updateButtons();
  message(view.status, 'Applying once…');
  const controller = new AbortController();
  const deadline = setTimeout(() => controller.abort(), 10000);
  try {
    const snapshot = await request(view.path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (view.version === submittedVersion) view.dirty = false;
    view.saving = false;
    if (!stopped) {
      render(snapshot);
      message(view.status, view.dirty ? 'Submitted values applied. Newer edits remain unsaved.' : 'Applied to the simulated environment.');
    }
  } catch (error) {
    view.dirty = true;
    message(view.status, `${error.message} Not retried. A lost response may mean the operation applied; check the applied readback before submitting again.`, true);
  } finally {
    clearTimeout(deadline);
    view.saving = false;
    writing = false;
    updateButtons();
  }
}

function render(snapshot) {
  latest = snapshot;
  for (const view of views) {
    if (!view.dirty && !view.saving && !view.form.contains(document.activeElement)) {
      view.sync(snapshot);
      if (!view.status.classList.contains('error')) message(view.status, 'Showing applied environment; edits require Apply.');
    }
  }
  byId('input-environment').textContent = `Applied external raw levels: ${hex(snapshot.inputs.raw)} · config: ${hex(snapshot.inputs.config)} · polarity: ${hex(snapshot.inputs.polarity)}`;
  for (const [device, view] of deviceViews) {
    view.actual.textContent = `Applied state: ${snapshot.devices[device].online ? 'online' : 'OFFLINE — injected bus fault'}`;
  }
  const io = snapshot.observed.io;
  const actualIO = io.available ? io.value : null;
  message(byId('io-status'), actualIO ? 'Available — fresh original driver read.' : 'Unavailable — values below are unknown, not zero.');
  showError(byId('io-error'), actualIO ? '' : `I/O unavailable: ${io.error || 'No decoded response.'}`);
  inputReadbacks.forEach((node, index) => {
    const active = actualIO?.inputs.active[index];
    node.textContent = `Input ${index + 1}: ${typeof active === 'boolean' ? (active ? 'ACTIVE' : 'idle') : 'unknown'}`;
  });
  relayReadbacks.forEach((node, index) => {
    const on = actualIO?.relays.on[index];
    node.textContent = `Relay ${index + 1}: ${typeof on === 'boolean' ? (on ? 'ON signal' : 'off signal') : 'unknown'}`;
  });
  byId('io-raw').textContent = actualIO ? `Decoded input raw: ${hex(actualIO.inputs.raw)} · relay port: ${hex(actualIO.relays.raw)}` : 'Decoded raw ports: unavailable.';
  const clock = snapshot.observed.clock;
  const actualClock = clock.available ? clock.value : null;
  byId('clock-readback').textContent = actualClock
    ? `Actual decoded clock: ${actualClock.datetime} · ${actualClock.valid ? 'valid (OSF clear)' : 'UNTRUSTED (OSF set)'}`
    : 'Actual decoded clock: unavailable — no fabricated timestamp.';
  showError(byId('clock-error'), actualClock ? '' : `Clock unavailable: ${clock.error || 'No decoded response.'}`);
  byId('rtc-environment').textContent = `Applied RTC model: ${snapshot.devices.rtc.datetime} · OSF ${snapshot.devices.rtc.osf ? 'set' : 'clear'} (synthetic environment, not a separate clock setter).`;
  const lcd = snapshot.lcd;
  const task = snapshot.observed.lcd_task;
  byId('lcd-task').textContent = `Original LCD task: ${task}`;
  showError(byId('lcd-restart'), task === 'unavailable' || task === 'stopped'
    ? 'LCD drawing has stopped. Restoring online alone cannot restart the task; restart the simulator process. The canvas may retain the last frame.' : '');
  byId('lcd-metadata').textContent = `${lcd.width} × ${lcd.height} · frames: ${lcd.frames} · checksum: ${lcd.checksum} · online: ${lcd.online} · backlight: ${lcd.backlight} · sleeping: ${lcd.sleeping}`;
  updateButtons();
}

async function startLcd() {
  const session = ++lcdGeneration;
  try {
    const {CanvasRenderer, WebSocketClient} = await import('/display/static/framebuf-canvas.js');
    if (stopped || session !== lcdGeneration) return;
    lcdRenderer = new CanvasRenderer('lcd-displays', {minDimension: 240});
    const url = new URL('/display/ws', location.href);
    url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    lcdClient = new WebSocketClient(url.href);
    lcdClient.onConnect(() => {
      lcdRenderer.reset();
      showError(byId('lcd-error'), '');
    });
    lcdClient.onMessage((frame) => lcdRenderer.handleMessage(frame));
    lcdClient.onStateChange((state) => {
      message(byId('lcd-status'), `LCD stream: ${state}${state === 'connected' ? '' : ' — canvas may show a stale frame'}`);
    });
    lcdClient.onError((error) => showError(byId('lcd-error'), `LCD stream: ${error.message}`));
    lcdClient.connect();
  } catch (error) {
    if (!stopped && session === lcdGeneration) showError(byId('lcd-error'), `Cannot start LCD viewer: ${error.message}`);
  }
}

window.addEventListener('pagehide', () => {
  stopped = true;
  lcdGeneration += 1;
  clearTimeout(timer);
  reading?.abort();
  lcdClient?.disconnect();
  lcdRenderer?.destroy();
  lcdClient = null;
  lcdRenderer = null;
});
window.addEventListener('pageshow', (event) => {
  if (!event.persisted) return;
  stopped = false;
  poll();
  startLcd();
});
updateButtons();
poll();
startLcd();
