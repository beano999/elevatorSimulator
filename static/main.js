const floorsEl = document.getElementById('floors');
const dirEl = document.getElementById('dir');
const currentEl = document.getElementById('currentFloor');
const targetEl = document.getElementById('activeTarget');
const queueSizeEl = document.getElementById('queueSize');
const queueChipsEl = document.getElementById('queueChips');
const floorCountEl = document.getElementById('floorCount');
const logEl = document.getElementById('log');

let latestState = null;

function log(msg) {
  const p = document.createElement('p');
  p.className = 'log-line';
  p.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  logEl.prepend(p);
  const lines = logEl.querySelectorAll('.log-line');
  if (lines.length > 80) lines[lines.length - 1].remove();
}

async function fetchState() {
  try {
    const res = await fetch('/state');
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    latestState = data;
    renderState(data);
  } catch (err) {
    log(`State error: ${err}`);
  }
}

async function requestFloor(floor) {
  try {
    const res = await fetch('/request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ floor })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);
    log(data.message || `Requested floor ${floor}`);
    renderState(data.state || latestState);
  } catch (err) {
    log(`Request error: ${err}`);
  }
}

function renderState(state) {
  if (!state) return;
  dirEl.textContent = `Direction: ${state.direction}`;
  currentEl.textContent = state.currentFloor;
  targetEl.textContent = state.activeTarget ?? '-';
  queueSizeEl.textContent = state.queue.length;
  floorCountEl.textContent = `${state.numFloors} floors`;

  queueChipsEl.innerHTML = '';
  state.queue.forEach(f => {
    const chip = document.createElement('div');
    chip.className = 'chip';
    chip.textContent = `Queued: ${f}`;
    queueChipsEl.appendChild(chip);
  });

  floorsEl.innerHTML = '';
  // Render highest at top for elevator feel.
  [...state.floors].reverse().forEach(info => {
    const btn = document.createElement('button');
    btn.className = 'floor';
    btn.textContent = info.floor;
    btn.onclick = () => requestFloor(info.floor);
    if (info.state === 'Current') btn.classList.add('state-current');
    if (info.state === 'Moving') btn.classList.add('state-moving');
    if (info.state === 'Queued') btn.classList.add('state-queued');
    const disableStates = ['Queued', 'Moving', 'Current'];
    if (disableStates.includes(info.state)) btn.disabled = true;
    floorsEl.appendChild(btn);
  });
}

fetchState();
setInterval(fetchState, 500);
