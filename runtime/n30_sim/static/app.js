// SPDX-License-Identifier: MIT
// All displayed outputs come from the server's shared controllers and cache.
const byId = (id) => document.getElementById(id);
const pinViews = new Map();
const bankViews = new Map();
let latest = null;
let stopped = false;
let timer = null;
let reading = null;
let writing = false;
let generation = 0;
let oledClient = null;
let oledRenderer = null;
let oledGeneration = 0;

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

function value(number, digits = 3) {
  return typeof number === 'number' && Number.isFinite(number) ? number.toFixed(digits) : '—';
}

function addOption(select, label, optionValue) {
  const option = element('option', label);
  option.value = optionValue;
  select.append(option);
}

function trackEdits(view) {
  view.dirty = false;
  view.version = 0;
  const changed = () => {
    view.dirty = true;
    view.version += 1;
    if (!view.saving) message(view.status, 'Unsaved edits — not applied.');
  };
  view.form.addEventListener('input', changed);
  view.form.addEventListener('change', changed);
}

function canSync(view) {
  return !view.dirty && !view.saving && !view.form.contains(document.activeElement);
}

function updateButtons() {
  for (const view of pinViews.values()) {
    const isInput = view.pin.mode === 'input';
    view.select.disabled = !isInput;
    view.save.disabled = writing || !isInput;
  }
  for (const view of bankViews.values()) {
    view.save.disabled = writing;
    view.discard.disabled = writing;
  }
}

async function request(path, options = {}) {
  const response = await fetch(path, {cache: 'no-store', ...options});
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(`HTTP ${response.status}: server did not return JSON.`);
  }
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${data.error?.message || response.statusText}`);
  }
  return data;
}

// There is one GET at a time. Generation invalidates a read begun before a save.
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
      message(byId('connection-status'), `Connected · last snapshot ${new Date().toLocaleTimeString()} · refresh about once per second`);
    }
  } catch (error) {
    if (!stopped && started === generation) {
      showError(byId('network-error'), `Refresh failed: ${error.message} Displayed values may be stale; unsaved edits are preserved.`);
      message(byId('connection-status'), 'Disconnected or stale — waiting for the next read.');
    }
  } finally {
    clearTimeout(deadline);
    reading = null;
    if (!stopped) timer = setTimeout(poll, 1000);
  }
}

// Never retry a POST. A lost response can mean the server applied the request.
async function save(view, path, payload) {
  if (writing || stopped) return;
  const submittedVersion = view.version;
  writing = true;
  view.saving = true;
  generation += 1;
  updateButtons();
  message(view.status, 'Applying once…');
  try {
    const snapshot = await request(path, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (view.version === submittedVersion) view.dirty = false;
    view.saving = false;
    render(snapshot);
    message(view.status, view.dirty
      ? 'Submitted values applied. Newer edits remain unsaved.'
      : 'Applied. Meter changes appear in decoded readings after the next poll.');
  } catch (error) {
    message(view.status, `${error.message} Request was not retried. If the connection failed, check injected values before submitting again.`, true);
  } finally {
    view.saving = false;
    writing = false;
    updateButtons();
  }
}

function createPin(pin) {
  const card = element('article', undefined, 'card');
  const heading = element('h3', `GPIO ${pin.pin}`);
  const name = element('p', pin.name, 'muted');
  const values = element('dl', undefined, 'pin-values');
  const fields = {};
  for (const label of ['Direction', 'Raw level', 'Output command', 'Pull']) {
    const term = element('dt', label);
    fields[label] = element('dd', 'Waiting');
    values.append(term, fields[label]);
  }
  const hint = element('p', undefined, 'hint');
  const form = element('form');
  const label = element('label', 'Requested external input level');
  const select = element('select');
  select.id = `pin-${pin.pin}-level`;
  select.required = true;
  label.htmlFor = select.id;
  addOption(select, 'Choose a level…', '');
  addOption(select, 'Release external drive', 'release');
  addOption(select, 'Low (0)', '0');
  addOption(select, 'High (1)', '1');
  const saveButton = element('button', `Apply GPIO ${pin.pin} input`);
  saveButton.type = 'submit';
  const actions = element('div', undefined, 'actions');
  actions.append(saveButton);
  const status = element('p', 'No input request made in this page.', 'form-status');
  status.setAttribute('role', 'status');
  form.append(label, select, actions, status);
  card.append(heading, name, values, hint, form);
  byId('pins').append(card);
  const view = {pin, form, select, fields, name, hint, status, save: saveButton};
  trackEdits(view);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!form.reportValidity() || view.pin.mode !== 'input') return;
    const level = select.value === 'release' ? null : Number(select.value);
    await save(view, `/sim/api/inputs/${pin.pin}`, {level});
    if (!status.classList.contains('error') && !view.dirty) {
      message(status, `Applied external request: ${level === null ? 'release' : level}. Raw shared level is shown above.`);
    }
  });
  pinViews.set(pin.pin, view);
  return view;
}

function numberInput(id, min, max, step) {
  const input = element('input');
  input.type = 'number';
  input.id = id;
  input.min = String(min);
  input.max = String(max);
  input.step = String(step);
  input.required = true;
  input.inputMode = 'decimal';
  return input;
}

function createBank(bank) {
  const card = element('article', undefined, 'card');
  const heading = element('h3', `Meter bank ${bank.bank}`);
  const target = element('p', undefined, 'target-note');
  const observed = element('p', 'Actual decoder: waiting.', 'decoded-note');
  const form = element('form');
  form.setAttribute('aria-label', `Bank ${bank.bank} environment`);
  const wrap = element('div', undefined, 'table-wrap');
  const table = element('table');
  const caption = element('caption', 'Staged edits vs applied environment vs real decoded cache');
  const head = element('thead');
  const header = element('tr');
  for (const [text, style] of [['Channel', ''], ['Staged A', 'target'], ['Injected A', 'target'], ['Decoded A', 'decoded']]) {
    const cell = element('th', text, style);
    cell.scope = 'col';
    header.append(cell);
  }
  head.append(header);
  const body = element('tbody');
  const currents = [];
  const injected = [];
  const decoded = [];
  for (let index = 0; index < 10; index += 1) {
    const channel = (bank.bank - 1) * 10 + index + 1;
    const row = element('tr');
    const cell = element('th');
    cell.scope = 'row';
    const label = element('label', `CH ${channel}`);
    const input = numberInput(`bank-${bank.bank}-ch-${channel}`, 0, 4294967.295, 0.001);
    input.className = 'current-input';
    label.htmlFor = input.id;
    input.setAttribute('aria-label', `Channel ${channel} staged current in amperes`);
    cell.append(label);
    const editCell = element('td', undefined, 'target');
    editCell.append(input);
    const injectedCell = element('td', '—', 'target');
    const decodedCell = element('td', '—', 'decoded');
    row.append(cell, editCell, injectedCell, decodedCell);
    body.append(row);
    currents.push(input);
    injected.push(injectedCell);
    decoded.push(decodedCell);
  }
  table.append(caption, head, body);
  wrap.append(table);
  const fieldset = element('fieldset');
  fieldset.append(element('legend', 'Staged environment settings'));
  const fields = element('div', undefined, 'bank-fields');
  const voltage = numberInput(`bank-${bank.bank}-voltage`, 0, 655.35, 0.01);
  const frequency = numberInput(`bank-${bank.bank}-frequency`, 0, 655.35, 0.01);
  for (const [text, input] of [['Voltage (V)', voltage], ['Frequency (Hz)', frequency]]) {
    const container = element('div');
    const label = element('label', text);
    label.htmlFor = input.id;
    container.append(label, input);
    fields.append(container);
  }
  const faultContainer = element('div', undefined, 'fault-field');
  const faultLabel = element('label', 'Response fault');
  const fault = element('select');
  fault.id = `bank-${bank.bank}-fault`;
  faultLabel.htmlFor = fault.id;
  addOption(fault, 'Normal — valid response', 'normal');
  addOption(fault, 'Timeout — no response', 'timeout');
  addOption(fault, 'CRC — corrupt response checksum', 'crc');
  faultContainer.append(faultLabel, fault);
  fields.append(faultContainer);
  fieldset.append(fields);
  const actions = element('div', undefined, 'actions');
  const saveButton = element('button', `Save bank ${bank.bank}`);
  saveButton.type = 'submit';
  const discard = element('button', 'Discard edits', 'secondary');
  discard.type = 'button';
  actions.append(saveButton, discard);
  const status = element('p', 'No unsaved edits.', 'form-status');
  status.setAttribute('role', 'status');
  form.append(wrap, fieldset, actions, status);
  const rawDetails = element('details');
  rawDetails.append(element('summary', 'Actual decoder raw register words'));
  const raw = element('p', 'Unavailable', 'muted');
  rawDetails.append(raw);
  card.append(heading, target, observed, form, rawDetails);
  byId('banks').append(card);
  const view = {bank: bank.bank, form, target, observed, currents, injected, decoded,
    voltage, frequency, fault, status, raw, save: saveButton, discard};
  trackEdits(view);
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    save(view, `/sim/api/banks/${bank.bank}`, {
      currents_A: currents.map((input) => Number(input.value)),
      voltage_V: Number(voltage.value),
      frequency_Hz: Number(frequency.value),
      fault: fault.value,
    });
  });
  discard.addEventListener('click', () => {
    const current = latest?.banks.find((item) => item.bank === bank.bank);
    if (!current) return;
    syncBank(view, current);
    view.version += 1;
    view.dirty = false;
    message(status, 'Edits discarded; showing the latest applied environment.');
  });
  bankViews.set(bank.bank, view);
  return view;
}

function syncBank(view, bank) {
  bank.currents_A.forEach((current, index) => { view.currents[index].value = String(current); });
  view.voltage.value = String(bank.voltage_V);
  view.frequency.value = String(bank.frequency_Hz);
  view.fault.value = bank.fault;
}

function render(snapshot) {
  latest = snapshot;
  for (const pin of snapshot.pins) {
    const view = pinViews.get(pin.pin) || createPin(pin);
    view.pin = pin;
    view.name.textContent = pin.name;
    view.fields.Direction.textContent = pin.mode;
    view.fields['Raw level'].textContent = pin.level === null ? 'Unknown / undriven' : `${pin.level} (${pin.level === 1 ? 'high' : 'low'})`;
    view.fields['Output command'].textContent = pin.output === null ? 'Not an output' : (pin.output ? 'High' : 'Low');
    view.fields.Pull.textContent = pin.pull;
    view.hint.textContent = pin.mode === 'input'
      ? 'External input injection enabled. Selection is a request, not a readback.'
      : 'Read-only output. Change its mode or output in the original device UI; injection is blocked.';
  }
  byId('pins').setAttribute('aria-busy', 'false');
  for (const bank of snapshot.banks) {
    const view = bankViews.get(bank.bank) || createBank(bank);
    const actual = snapshot.observed?.banks?.find((item) => item.bank === bank.bank);
    if (canSync(view)) syncBank(view, bank);
    view.target.textContent = `Injected environment: ${value(bank.voltage_V, 2)} V · ${value(bank.frequency_Hz, 2)} Hz · fault ${bank.fault}`;
    bank.currents_A.forEach((current, index) => {
      view.injected[index].textContent = value(current);
      const channel = (bank.bank - 1) * 10 + index + 1;
      const decoded = actual?.channels?.find((item) => item.channel === channel);
      view.decoded[index].textContent = actual?.available ? value(decoded?.current_A) : '—';
    });
    const age = actual?.age_ms == null ? 'age unknown' : `age ${value(actual.age_ms / 1000, 1)} s`;
    const error = actual?.error ? ` · error: ${String(actual.error)}` : '';
    view.observed.textContent = actual?.available
      ? `Actual decoder: available · ${age} · ${value(actual.voltage_V, 2)} V · ${value(actual.frequency_Hz, 2)} Hz${error}`
      : `Actual decoder: unavailable · ${age}${error} · no decoded values (not zero).`;
    view.observed.classList.toggle('error', !actual?.available);
    view.raw.textContent = actual?.registers ? actual.registers.join(', ') : 'Unavailable — no decoded register cache.';
  }
  byId('banks').setAttribute('aria-busy', 'false');
  const oled = snapshot.oled;
  byId('oled-metadata').textContent = `${oled.width}×${oled.height} · ${oled.frames} published frames · power ${oled.powered ? 'on' : 'off'} · contrast ${oled.contrast} · inverted ${oled.inverted ? 'yes' : 'no'} · checksum ${oled.checksum}`;
  const modbus = snapshot.modbus;
  byId('modbus-metadata').textContent = `Requests ${modbus.requests} · responses ${modbus.responses} · CRC errors / injected faults ${modbus.crc_errors} · protocol exceptions ${modbus.exceptions}`;
  updateButtons();
}

async function startOled() {
  const session = ++oledGeneration;
  try {
    const {CanvasRenderer, WebSocketClient} = await import('/display/static/framebuf-canvas.js');
    if (stopped || session !== oledGeneration) return;
    oledRenderer = new CanvasRenderer('oled-displays', {minDimension: 128});
    const url = new URL('/display/ws', location.href);
    url.protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    oledClient = new WebSocketClient(url.href);
    oledClient.onConnect(() => {
      oledRenderer.reset();
      showError(byId('oled-error'), '');
    });
    oledClient.onMessage((frame) => oledRenderer.handleMessage(frame));
    oledClient.onStateChange((state) => {
      message(byId('oled-status'), `OLED stream: ${state}${state === 'connected' ? '' : ' — canvas may show a stale frame'}`);
    });
    oledClient.onError((error) => showError(byId('oled-error'), `OLED stream: ${error.message}`));
    oledClient.connect();
  } catch (error) {
    if (!stopped && session === oledGeneration) showError(byId('oled-error'), `Cannot start OLED viewer: ${error.message}`);
  }
}

window.addEventListener('pagehide', () => {
  stopped = true;
  oledGeneration += 1;
  clearTimeout(timer);
  reading?.abort();
  oledClient?.disconnect();
  oledRenderer?.destroy();
  oledClient = null;
  oledRenderer = null;
});
window.addEventListener('pageshow', (event) => {
  if (!event.persisted) return;
  stopped = false;
  poll();
  startOled();
});
poll();
startOled();
