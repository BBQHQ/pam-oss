// PAM — Frontend

const API = '';

// ─── DOM ────────────────────────────────────────────

// To-dos
const todoInput = document.getElementById('todoInput');
const todoAddBtn = document.getElementById('todoAddBtn');
const todoList = document.getElementById('todoList');
const todoShowDone = document.getElementById('todoShowDone');

// Tasks
const taskInput = document.getElementById('taskInput');
const taskSubmitBtn = document.getElementById('taskSubmitBtn');
const taskInputMeta = document.getElementById('taskInputMeta');
const needsOkList = document.getElementById('needsOkList');
const needsOkCount = document.getElementById('needsOkCount');
const activeTaskList = document.getElementById('activeTaskList');
// Tasks page (full view)
const needsOkSectionFull = document.getElementById('needsOkSectionFull');
const needsOkCountFull = document.getElementById('needsOkCountFull');
const needsOkListFull = document.getElementById('needsOkListFull');
const allTaskList = document.getElementById('allTaskList');

// Voice
const recordBtn = document.getElementById('recordBtn');
const micIcon = document.getElementById('micIcon');
const stopIcon = document.getElementById('stopIcon');
const recordLabel = document.getElementById('recordLabel');
const timer = document.getElementById('timer');
const waveform = document.getElementById('waveform');
const waveCanvas = document.getElementById('waveCanvas');
const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');
const browseBtn = document.getElementById('browseBtn');
const processing = document.getElementById('processing');
const resultCard = document.getElementById('resultCard');
const resultText = document.getElementById('resultText');
const duration = document.getElementById('duration');
const copyBtn = document.getElementById('copyBtn');
const sendToTodoBtn = document.getElementById('sendToTodoBtn');
const sendToTaskBtn = document.getElementById('sendToTaskBtn');
const error = document.getElementById('error');
const errorText = document.getElementById('errorText');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');

// State
let mediaRecorder = null;
let audioChunks = [];
let timerInterval = null;
let warmupHeartbeat = null;
let startTime = 0;
let audioContext = null;
let analyser = null;
let animFrame = null;
let showingDone = false;
let matchDebounce = null;
let editingNoteId = null;
let noteSavedTitle = '';
let noteSavedContent = '';

// ─── Navigation ─────────────────────────────────────

const pageTitles = {
  dashboard: ['Dashboard', 'Overview of your tasks and to-dos'],
  todos: ['To-Dos', 'Checklists and categories'],
  voice: ['Voice', 'Record or upload audio for transcription'],
  notes: ['Notes', 'Quick notes and saved thoughts'],
  calendar: ['Calendar', 'Events, invites, and calendar holds'],
  projects: ['Projects', 'Kanban boards — track what matters across domains'],
  tasks: ['PAM Tasks', 'PAM automation tasks and project routing'],
  accomplishments: ['Wins', 'Things you have actually done. Receipts.'],
  settings: ['Settings', 'PAM preferences — schedules, notifications, UI'],
  'prompt-zone': ['Prompt Zone', 'Your prompt library. Star a prompt to make it golden.'],
  habits: ['Habits', 'Recurring goals with streak tracking. No stacking, no guilt.'],
  gratitude: ['Gratitude', 'What matters most. Pillars of life and evidence of progress.'],
};

function showSection(name) {
  // Check for unsaved note
  if (noteEditorView.style.display !== 'none' && hasUnsavedNote()) {
    if (!confirm('You have an unsaved note. Leave without saving?')) return;
  }

  document.querySelectorAll('.page').forEach(p => p.classList.add('hidden'));
  document.getElementById(`page-${name}`).classList.remove('hidden');
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelectorAll(`.nav-item[data-section="${name}"]`).forEach(n => n.classList.add('active'));
  document.getElementById('pageTitle').textContent = pageTitles[name][0];
  document.getElementById('pageSub').textContent = pageTitles[name][1];
  if (name === 'accomplishments') loadWins();
  if (name === 'voice') loadRecentVoice();
  if (name === 'prompt-zone') loadPromptZone();
  if (name === 'todos') loadTodoPage();
  if (name === 'habits') loadHabitsPage();
  if (name === 'gratitude') loadGratitudePage();
}

// ─── Whisper Status ─────────────────────────────────

async function checkWhisperStatus() {
  const mobileDot = document.getElementById('statusDotMobile');
  try {
    const resp = await fetch(`${API}/voice/status`);
    const data = await resp.json();
    if (data.running) {
      statusDot.className = 'status-dot loaded';
      if (mobileDot) mobileDot.className = 'status-dot loaded';
      statusText.textContent = `Whisper running`;
    } else {
      statusDot.className = 'status-dot unloaded';
      if (mobileDot) mobileDot.className = 'status-dot unloaded';
      statusText.textContent = 'Whisper standby';
    }
  } catch {
    statusDot.className = 'status-dot error';
    if (mobileDot) mobileDot.className = 'status-dot error';
    statusText.textContent = 'Offline';
  }
}

function fmtTime(s) {
  return `${String(Math.floor(s/60)).padStart(2,'0')}:${String(s%60).padStart(2,'0')}`;
}

// ═══════════════════════════════════════════════════
// TO-DO LIST
// ═══════════════════════════════════════════════════

todoAddBtn.addEventListener('click', addTodo);
todoInput.addEventListener('keydown', e => { if (e.key === 'Enter') addTodo(); });

todoShowDone.addEventListener('click', () => {
  showingDone = !showingDone;
  todoShowDone.textContent = showingDone ? 'Hide done' : 'Show done';
  loadTodos();
});

async function addTodo() {
  const text = todoInput.value.trim();
  if (!text) return;
  todoAddBtn.disabled = true;
  playSFX('create');
  await fetch(`${API}/todos/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  todoInput.value = '';
  todoAddBtn.disabled = false;
  loadTodos();
}

async function loadTodos() {
  try {
    const resp = await fetch(`${API}/todos/?show_done=${showingDone}`);
    const todos = await resp.json();

    const allResp = await fetch(`${API}/todos/?show_done=true`);
    const allTodos = await allResp.json();
    const hasDone = allTodos.some(t => t.done);
    todoShowDone.style.display = hasDone ? 'block' : 'none';

    // Filter out sub-tasks (shown on the To-Dos page, not here)
    const topLevel = todos.filter(t => !t.parent_id);

    // Sort: categorized first, then uncategorized
    topLevel.sort((a, b) => {
      const ac = a.category || '';
      const bc = b.category || '';
      if (ac && !bc) return -1;
      if (!ac && bc) return 1;
      return ac.localeCompare(bc);
    });

    if (topLevel.length === 0) {
      todoList.innerHTML = '<p class="empty">Nothing here yet.</p>';
      return;
    }

    todoList.innerHTML = topLevel.map(t => `
      <div class="todo-item">
        <button class="todo-checkbox ${t.done ? 'checked' : ''}"
                onclick="toggleTodo('${t.id}', ${t.done})">${t.done ? '&#10003;' : ''}</button>
        ${t.category ? `<span class="todo-cat-badge">${esc(t.category)}</span>` : ''}
        <span class="todo-text ${t.done ? 'done' : ''}">${esc(t.text)}</span>
        <button class="todo-delete" onclick="deleteTodo('${t.id}')">&#10005;</button>
      </div>
    `).join('');
  } catch {
    todoList.innerHTML = '<p class="empty">Failed to load.</p>';
  }
}

// ─── Sound Effects ─────────────────────────────────
const PAM_SFX = {
  create: [
    '/static/sounds/yoshi-tongue.mp3',
    '/static/sounds/mac-quack.mp3',
    '/static/sounds/dkc2-kritter.mp3',
    '/static/sounds/check-mark.mp3',
    '/static/sounds/magic-fairy.mp3',
    '/static/sounds/dragon-ball-z-budokai-tenkaichi-2-select-sfx-65004.mp3',
    '/static/sounds/silent-hill-2-receiving-item.mp3',
    '/static/sounds/anime-magic-sound-effect-96497.mp3',
    '/static/sounds/anime-tututru-33951.mp3',
    '/static/sounds/fears-to-fathom-notification-sound-46473.mp3',
  ],
  complete: [
    '/static/sounds/metal-gear-alert.mp3',
    '/static/sounds/punch.mp3',
    '/static/sounds/pizza-tower-taunt.mp3',
    '/static/sounds/anime-punch.mp3',
    '/static/sounds/sonic-badnik-death.mp3',
    '/static/sounds/starcraft-confirm-34953.mp3',
    '/static/sounds/wii-copy-finish-sound-34420.mp3',
    '/static/sounds/rizz-sound-effect-54189.mp3',
    '/static/sounds/pew-loud-boom-44976.mp3',
  ],
  delete: [
    '/static/sounds/sonic-death.mp3',
    '/static/sounds/minecraft-death.mp3',
    '/static/sounds/kirby-death.mp3',
    '/static/sounds/lego-yoda-death.mp3',
    '/static/sounds/megaman-x-death.mp3',
    '/static/sounds/spongebob-boowomp.mp3',
    '/static/sounds/price-is-right-losing.mp3',
    '/static/sounds/incorrect-sound-effect-88070.mp3',
    '/static/sounds/boo-womp-spongbob-sound-effect-66699.mp3',
  ],
  utility: [
    '/static/sounds/spongebob-duck.mp3',
    '/static/sounds/death-note-confusion.mp3',
    '/static/sounds/teleport-sound.mp3',
    '/static/sounds/silent-hill-2-ui-sound-72491.mp3',
    '/static/sounds/earthbound-partners-turn-6957.mp3',
    '/static/sounds/old-steam-chat-notification-61.mp3',
    '/static/sounds/quake-jump-dah-sarge-49873.mp3',
    '/static/sounds/sonic-1-teleport-2287.mp3',
  ],
  epic: [
    '/static/sounds/kamehameha-wave-sound-effect.mp3',
    '/static/sounds/goldeneye-n64-music-bong-recreation-55824.mp3',
    '/static/sounds/anime-wow.mp3',
    '/static/sounds/awkward-pause-anime-sounds-3397.mp3',
    '/static/sounds/anime-eurobeat-65242.mp3',
    '/static/sounds/what-bottom-text-meme-sanctuary-guardian-s-24591.mp3',
  ],
};
const PAM_SETTINGS = { sfx_enabled: true, sfx_volume: 0.6 };
function playSFX(category) {
  try {
    if (!PAM_SETTINGS.sfx_enabled) return;
    const pool = PAM_SFX[category];
    if (!pool) return;
    const src = pool[Math.floor(Math.random() * pool.length)];
    const audio = new Audio(src);
    audio.volume = PAM_SETTINGS.sfx_volume;
    audio.play().catch(() => {});
  } catch {}
}

async function toggleTodo(id, wasDone) {
  // Only play sound when transitioning undone → done
  if (!wasDone) playSFX('complete');
  // Refresh dashboard wins after toggle since todo done flows into accomplishments
  setTimeout(() => loadDashboardWins(), 200);
  await fetch(`${API}/todos/${id}/toggle`, { method: 'POST' });
  loadTodos();
}

async function deleteTodo(id) {
  playSFX('delete');
  await fetch(`${API}/todos/${id}`, { method: 'DELETE' });
  loadTodos();
}

// ═══════════════════════════════════════════════════
// TO-DOS PAGE (categories + sub-tasks)
// ═══════════════════════════════════════════════════

const todoCategoryInput = document.getElementById('todoCategoryInput');
const todoCategoryAddBtn = document.getElementById('todoCategoryAddBtn');
const todoCategoryList = document.getElementById('todoCategoryList');

if (todoCategoryAddBtn) {
  todoCategoryAddBtn.addEventListener('click', addTodoCategory);
  todoCategoryInput.addEventListener('keydown', e => { if (e.key === 'Enter') addTodoCategory(); });
}

async function addTodoCategory() {
  const name = todoCategoryInput.value.trim();
  if (!name) return;
  todoCategoryInput.value = '';
  // Just reload — empty categories appear once they have an item
  // For now, focus the page so user can add items via the inline input
  await fetch(`${API}/todos/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text: '(new)', category: name }),
  });
  loadTodoPage();
}

async function loadTodoPage() {
  try {
    const resp = await fetch(`${API}/todos/grouped`);
    const grouped = await resp.json();
    const catNames = Object.keys(grouped).sort((a, b) => {
      if (a === '') return 1;
      if (b === '') return -1;
      return a.localeCompare(b);
    });

    if (catNames.length === 0) {
      todoCategoryList.innerHTML = '<p class="empty">No to-dos yet. Add a category above or use the dashboard quick-add.</p>';
      return;
    }

    let html = '';
    for (const cat of catNames) {
      const data = grouped[cat];
      const items = data.items || [];
      const doneCount = data.done_count || 0;
      const label = cat || 'Uncategorized';
      const openCount = items.reduce((n, t) => n + 1 + (t.subtasks || []).length, 0);

      html += `<div class="todo-section" data-category="${esc(cat)}">`;
      html += `<div class="todo-section-header" onclick="toggleCategoryCollapse(this)">
        <span class="todo-category-arrow">&#9660;</span>
        <span class="todo-section-label">${esc(label)}</span>
        <span class="todo-section-meta">${openCount} open${doneCount ? ` · <a class="todo-done-toggle" onclick="event.stopPropagation();toggleDoneSection(this.closest(\'.todo-section\'),\'${esc(cat)}\')">${doneCount} done</a>` : ''}</span>
      </div>`;
      html += `<div class="todo-section-body">`;

      for (const t of items) {
        html += renderTodoItem(t, cat);
        if (t.subtasks) {
          for (const sub of t.subtasks) {
            html += renderTodoItem(sub, cat, true);
          }
        }
      }

      // Inline add input
      html += `<div class="todo-section-add">
        <input type="text" class="todo-cat-input" data-cat="${esc(cat)}" placeholder="Add to ${esc(label)}..." autocomplete="off"
               onkeydown="if(event.key==='Enter')addTodoToCategory(this)">
      </div>`;

      // Hidden done items container (loaded on demand)
      if (doneCount) {
        html += `<div class="todo-done-list" style="display:none"></div>`;
      }

      html += `</div></div>`;
    }

    todoCategoryList.innerHTML = html;
  } catch {
    todoCategoryList.innerHTML = '<p class="empty">Failed to load to-dos.</p>';
  }
}

function renderTodoItem(t, cat, isSub) {
  const cls = isSub ? 'todo-item todo-subtask-item' : 'todo-item';
  return `
    <div class="${cls}">
      <button class="todo-checkbox ${t.done ? 'checked' : ''}"
              onclick="toggleTodoPage('${t.id}', ${t.done})">${t.done ? '&#10003;' : ''}</button>
      <span class="todo-text ${t.done ? 'done' : ''}">${esc(t.text)}</span>
      <button class="todo-delete" onclick="deleteTodoPage('${t.id}')">&#10005;</button>
    </div>`;
}

function toggleCategoryCollapse(header) {
  const body = header.nextElementSibling;
  const arrow = header.querySelector('.todo-category-arrow');
  if (body.style.display === 'none') {
    body.style.display = '';
    arrow.innerHTML = '&#9660;';
  } else {
    body.style.display = 'none';
    arrow.innerHTML = '&#9654;';
  }
}

async function addTodoToCategory(input) {
  const text = input.value.trim();
  if (!text) return;
  playSFX('create');
  const cat = input.getAttribute('data-cat');
  await fetch(`${API}/todos/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, category: cat || null }),
  });
  input.value = '';
  loadTodoPage();
}

async function toggleDoneSection(sectionEl, cat) {
  const doneList = sectionEl.querySelector('.todo-done-list');
  if (!doneList) return;
  if (doneList.style.display !== 'none') {
    doneList.style.display = 'none';
    return;
  }
  // Fetch done items for this category
  const resp = await fetch(`${API}/todos/grouped?show_done=true`);
  const grouped = await resp.json();
  const data = grouped[cat];
  if (!data) return;
  const allItems = data.items || [];
  // Filter to only done top-level items and their done subtasks
  let html = '';
  for (const t of allItems) {
    if (t.done) {
      html += renderTodoItem(t, cat);
    }
    for (const sub of (t.subtasks || [])) {
      if (sub.done) {
        html += renderTodoItem(sub, cat, true);
      }
    }
  }
  if (!html) html = '<p class="empty" style="padding:0.5rem 0">No completed items.</p>';
  doneList.innerHTML = html;
  doneList.style.display = '';
}

async function toggleTodoPage(id, wasDone) {
  if (!wasDone) playSFX('complete');
  await fetch(`${API}/todos/${id}/toggle`, { method: 'POST' });
  setTimeout(() => loadDashboardWins(), 200);
  loadTodoPage();
  loadTodos();
}

async function deleteTodoPage(id) {
  playSFX('delete');
  await fetch(`${API}/todos/${id}`, { method: 'DELETE' });
  loadTodoPage();
  loadTodos();
}

// ═══════════════════════════════════════════════════
// PAM TASKS
// ═══════════════════════════════════════════════════

taskSubmitBtn.addEventListener('click', submitTask);
taskInput.addEventListener('keydown', e => { if (e.key === 'Enter') submitTask(); });

taskInput.addEventListener('input', () => {
  clearTimeout(matchDebounce);
  matchDebounce = setTimeout(async () => {
    const text = taskInput.value.trim();
    if (text.length < 3) { taskInputMeta.innerHTML = ''; return; }
    try {
      const resp = await fetch(`${API}/projects/match?text=${encodeURIComponent(text)}`);
      const data = await resp.json();
      taskInputMeta.innerHTML = data.matched
        ? `Routes to: <span class="project-match">${data.project.name}</span>` : '';
    } catch {}
  }, 300);
});

async function submitTask() {
  const text = taskInput.value.trim();
  if (!text) return;
  taskSubmitBtn.disabled = true;
  playSFX('create');
  await fetch(`${API}/tasks/submit`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, source: 'dashboard', priority: 'normal' }),
  });
  taskInput.value = '';
  taskInputMeta.innerHTML = '';
  taskSubmitBtn.disabled = false;
  loadTasks();
}

async function loadQuestions() {
  try {
    const resp = await fetch(`${API}/questions/open`);
    const questions = await resp.json();
    const container = document.getElementById('pamQuestionsList');

    if (questions.length === 0) {
      container.innerHTML = '';
      return 0;
    }

    container.innerHTML = questions.map(q => `
      <div class="question-card" id="qcard-${q.id}">
        <div class="question-label">PAM Question</div>
        <div class="question-text">${esc(q.question)}</div>
        ${q.context ? `<div class="question-context">${esc(q.context)}</div>` : ''}
        <div class="question-answer-row">
          <input type="text" id="qanswer-${q.id}" placeholder="Your answer..." autocomplete="off">
          <button class="btn-primary" onclick="answerQuestion(${q.id})">Reply</button>
        </div>
        <button class="question-dismiss" onclick="dismissQuestion(${q.id})">Dismiss</button>
      </div>
    `).join('');

    return questions.length;
  } catch {
    return 0;
  }
}

async function answerQuestion(id) {
  const input = document.getElementById(`qanswer-${id}`);
  const answer = input.value.trim();
  if (!answer) { input.focus(); return; }
  const resp = await fetch(`${API}/questions/${id}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ answer }),
  });
  const result = await resp.json();
  playSFX('epic');
  loadDashboardAttention();

  // If the answered question belongs to the currently open note, refresh enhanced view
  if (result.source_task && editingNoteId) {
    const match = result.source_task.match(/^note:(\d+)$/);
    if (match && parseInt(match[1]) === editingNoteId) {
      loadEnhancedView();
    }
  }
}

async function dismissQuestion(id) {
  await fetch(`${API}/questions/${id}/dismiss`, { method: 'POST' });
  loadDashboardAttention();
}

async function loadDashboardAttention() {
  const qCount = await loadQuestions();
  await loadTasks();
  // loadTasks handles its own count, but we need to merge
  const stagedCount = document.querySelectorAll('#needsOkList .task-card').length;
  const total = qCount + stagedCount;
  const emptyEl = document.getElementById('attentionEmpty');
  if (total > 0) {
    needsOkCount.style.display = 'inline';
    needsOkCount.textContent = total;
    emptyEl.style.display = 'none';
  } else {
    needsOkCount.style.display = 'none';
    emptyEl.style.display = 'block';
  }
}

async function loadTasks() {
  try {
    const resp = await fetch(`${API}/tasks/`);
    const tasks = await resp.json();

    const staged = tasks.filter(t => t.status === 'staged');
    const active = tasks.filter(t => t.status === 'queued' || t.status === 'executing');
    const all = tasks.sort((a,b) => b.created.localeCompare(a.created));

    // Dashboard: staged tasks
    if (staged.length > 0) {
      needsOkList.innerHTML = staged.map(renderTask).join('');
    } else {
      needsOkList.innerHTML = '';
    }

    // Dashboard: Active tasks
    if (active.length > 0) {
      activeTaskList.innerHTML = active.sort((a,b) => b.created.localeCompare(a.created)).map(renderTask).join('');
    } else {
      activeTaskList.innerHTML = '<p class="empty">No active tasks.</p>';
    }

    // Tasks page: Needs OK (full)
    if (staged.length > 0) {
      needsOkSectionFull.style.display = 'block';
      needsOkCountFull.textContent = staged.length;
      needsOkListFull.innerHTML = staged.map(renderTask).join('');
    } else {
      needsOkSectionFull.style.display = 'none';
    }

    // Tasks page: All tasks
    if (all.length > 0) {
      allTaskList.innerHTML = all.map(renderTask).join('');
    } else {
      allTaskList.innerHTML = '<p class="empty">No tasks.</p>';
    }
  } catch {
    activeTaskList.innerHTML = '<p class="empty">Failed to load.</p>';
  }
}

function renderTask(t) {
  const tags = [];
  if (t.project) tags.push(`<span class="tag project">${t.project}</span>`);
  if (t.execution_type === 'claude') tags.push('<span class="tag claude">claude</span>');
  else if (t.execution_type === 'auto') tags.push('<span class="tag auto">auto</span>');

  let actions = '';
  if (t.status === 'staged') {
    actions = `
      <button class="action-btn ok" onclick="approveTask('${t.id}')">OK</button>
      <button class="action-btn no" onclick="rejectTask('${t.id}')">No</button>`;
  } else if (t.status !== 'done') {
    actions = `
      <button class="action-btn" onclick="completeTask('${t.id}')">Done</button>
      <button class="action-btn" onclick="deleteTask('${t.id}')">X</button>`;
  }

  return `
    <div class="task-card">
      <div class="task-dot ${t.status}"></div>
      <div class="task-info">
        <div class="task-title">${esc(t.title)}</div>
        ${tags.length ? `<div class="task-tags">${tags.join('')}</div>` : ''}
      </div>
      <div class="task-actions">${actions}</div>
    </div>`;
}

async function approveTask(id) {
  playSFX('complete');
  await fetch(`${API}/tasks/${id}/approve`, { method: 'POST' }); loadTasks();
}
async function rejectTask(id) {
  playSFX('delete');
  await fetch(`${API}/tasks/${id}/reject`, { method: 'POST' }); loadTasks();
}
async function completeTask(id) {
  playSFX('epic');
  await fetch(`${API}/tasks/${id}/done`, { method: 'POST' }); loadTasks();
}
async function deleteTask(id) {
  playSFX('delete');
  await fetch(`${API}/tasks/${id}`, { method: 'DELETE' }); loadTasks();
}

// ═══════════════════════════════════════════════════
// VOICE
// ═══════════════════════════════════════════════════

recordBtn.addEventListener('click', async () => {
  if (mediaRecorder && mediaRecorder.state === 'recording') stopRecording();
  else await startRecording();
});

async function startRecording() {
  try {
    fetch(`${API}/voice/warmup`, { method: 'POST' }).catch(() => {});
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      showError('Microphone requires HTTPS. On mobile, access PAM via localhost or set up HTTPS.');
      return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream, { mimeType: getSupportedMime() });
    audioChunks = [];

    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      stopVisualizer();
      const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType });
      await sendAudio(blob, 'recording.webm');
    };

    mediaRecorder.start(250);
    startTime = Date.now();
    // Heartbeat: keep whisper warm during long recordings (TTL is 5 min)
    warmupHeartbeat = setInterval(() => {
      fetch(`${API}/voice/warmup`, { method: 'POST' }).catch(() => {});
    }, 60000);
    recordBtn.classList.add('recording');
    micIcon.style.display = 'none'; stopIcon.style.display = 'block';
    recordLabel.textContent = 'Recording... click to stop';
    timer.style.display = 'block';
    hideResults();
    timerInterval = setInterval(() => {
      timer.textContent = fmtTime(Math.floor((Date.now() - startTime) / 1000));
    }, 250);
    startVisualizer(stream);
  } catch (err) { showError(`Microphone access denied: ${err.message}`); }
}

function stopRecording() {
  if (mediaRecorder && mediaRecorder.state === 'recording') {
    mediaRecorder.stop();
    clearInterval(timerInterval);
    if (warmupHeartbeat) { clearInterval(warmupHeartbeat); warmupHeartbeat = null; }
    recordBtn.classList.remove('recording');
    micIcon.style.display = 'block'; stopIcon.style.display = 'none';
    recordLabel.textContent = 'Click to record';
    timer.style.display = 'none'; waveform.style.display = 'none';
  }
}

function getSupportedMime() {
  for (const t of ['audio/webm;codecs=opus','audio/webm','audio/ogg','audio/mp4'])
    if (MediaRecorder.isTypeSupported(t)) return t;
  return 'audio/webm';
}

function startVisualizer(stream) {
  audioContext = new AudioContext();
  analyser = audioContext.createAnalyser(); analyser.fftSize = 256;
  audioContext.createMediaStreamSource(stream).connect(analyser);
  waveform.style.display = 'block';
  const ctx = waveCanvas.getContext('2d');
  const buf = new Uint8Array(analyser.frequencyBinCount);
  (function draw() {
    animFrame = requestAnimationFrame(draw);
    analyser.getByteTimeDomainData(buf);
    ctx.fillStyle = '#3d3d36'; ctx.fillRect(0,0,waveCanvas.width,waveCanvas.height);
    ctx.lineWidth = 2; ctx.strokeStyle = '#36f1cd'; ctx.beginPath();
    const sw = waveCanvas.width / buf.length;
    for (let i=0,x=0; i<buf.length; i++,x+=sw) {
      const y = (buf[i]/128) * waveCanvas.height/2;
      i===0 ? ctx.moveTo(x,y) : ctx.lineTo(x,y);
    }
    ctx.lineTo(waveCanvas.width, waveCanvas.height/2); ctx.stroke();
  })();
}

function stopVisualizer() {
  if (animFrame) cancelAnimationFrame(animFrame);
  if (audioContext) audioContext.close();
  audioContext = analyser = null;
}

browseBtn.addEventListener('click', e => { e.stopPropagation(); fileInput.click(); });
uploadZone.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', e => {
  if (e.target.files.length) { sendAudio(e.target.files[0], e.target.files[0].name); fileInput.value=''; }
});
uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('dragover'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
uploadZone.addEventListener('drop', e => {
  e.preventDefault(); uploadZone.classList.remove('dragover');
  if (e.dataTransfer.files.length) sendAudio(e.dataTransfer.files[0], e.dataTransfer.files[0].name);
});

async function sendAudio(blob, filename) {
  hideResults(); processing.style.display = 'flex';
  const fd = new FormData(); fd.append('file', blob, filename);
  try {
    const resp = await fetch(`${API}/voice/transcribe`, { method: 'POST', body: fd });
    const data = await resp.json();
    processing.style.display = 'none';
    if (data.error) showError(data.error);
    else { playSFX('complete'); showResult(data.text, data.duration_ms); loadRecentVoice(); voiceHistoryLoaded = false; }
  } catch (err) {
    processing.style.display = 'none';
    showError(`Failed to connect: ${err.message}`);
  }
  checkWhisperStatus();
}

sendToTodoBtn.addEventListener('click', async () => {
  const text = resultText.textContent.trim();
  if (!text) return;
  await fetch(`${API}/todos/`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  playSFX('create');
  sendToTodoBtn.textContent = 'Added!';
  setTimeout(() => { sendToTodoBtn.textContent = 'Add as To-Do'; }, 1500);
  loadTodos();
});

sendToTaskBtn.addEventListener('click', async () => {
  const text = resultText.textContent.trim();
  if (!text) return;
  await fetch(`${API}/tasks/submit`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text, source: 'voice', priority: 'normal' }),
  });
  playSFX('create');
  sendToTaskBtn.textContent = 'Submitted!';
  setTimeout(() => { sendToTaskBtn.textContent = 'Send as PAM Task'; }, 1500);
  loadTasks();
});

function showResult(text, ms) {
  resultText.textContent = text;
  duration.textContent = ms ? `${(ms/1000).toFixed(1)}s` : '';
  resultCard.classList.remove('hidden');
  error.style.display = 'none';
}
function showError(msg) {
  errorText.textContent = msg;
  error.style.display = 'block';
  resultCard.classList.add('hidden');
}
function hideResults() {
  resultCard.classList.add('hidden');
  error.style.display = 'none';
}

copyBtn.addEventListener('click', async () => {
  try { await navigator.clipboard.writeText(resultText.textContent); } catch { document.execCommand('copy'); }
  playSFX('utility');
  copyBtn.classList.add('copied'); setTimeout(() => copyBtn.classList.remove('copied'), 1500);
});

// ─── Voice History ─────────────────────────────────

const voiceRecordView = document.getElementById('voiceRecordView');
const voiceHistoryView = document.getElementById('voiceHistoryView');
const voiceRecentList = document.getElementById('voiceRecentList');
const voiceHistoryList = document.getElementById('voiceHistoryList');
const voiceHistoryCount = document.getElementById('voiceHistoryCount');
let voiceHistoryLoaded = false;

function showVoiceTab(tab) {
  document.querySelectorAll('#voiceTabs .board-tab').forEach(t => t.classList.remove('active'));
  if (tab === 'record') {
    document.querySelector('#voiceTabs .board-tab:first-child').classList.add('active');
    voiceRecordView.style.display = '';
    voiceHistoryView.style.display = 'none';
  } else {
    document.querySelector('#voiceTabs .board-tab:last-child').classList.add('active');
    voiceRecordView.style.display = 'none';
    voiceHistoryView.style.display = '';
    loadFullVoiceHistory();
  }
}

async function loadRecentVoice() {
  try {
    const resp = await fetch(`${API}/voice/history?limit=5&offset=0`);
    const data = await resp.json();
    const items = data.items || [];
    voiceRecentList.innerHTML = '';
    if (items.length === 0) {
      voiceRecentList.innerHTML = '<p class="empty">No transcriptions yet.</p>';
      return;
    }
    items.forEach(item => voiceRecentList.appendChild(buildVoiceLogItem(item)));
  } catch (err) {
    console.error('Failed to load recent voice:', err);
  }
}

async function loadFullVoiceHistory() {
  try {
    const resp = await fetch(`${API}/voice/history?limit=200&offset=0`);
    const data = await resp.json();
    const items = data.items || [];
    const total = data.total || 0;

    if (total > 0) {
      voiceHistoryCount.textContent = total;
      voiceHistoryCount.style.display = '';
    } else {
      voiceHistoryCount.style.display = 'none';
    }

    voiceHistoryList.innerHTML = '';
    if (items.length === 0) {
      voiceHistoryList.innerHTML = '<p class="empty">No transcriptions yet.</p>';
      return;
    }

    let lastDay = '';
    items.forEach(item => {
      const dt = new Date(item.created_at);
      const dayKey = dt.toLocaleDateString('en-US', { weekday: 'long', month: 'short', day: 'numeric' });
      if (dayKey !== lastDay) {
        const dayEl = document.createElement('div');
        dayEl.className = 'voice-log-day';
        dayEl.textContent = dayKey;
        voiceHistoryList.appendChild(dayEl);
        lastDay = dayKey;
      }
      voiceHistoryList.appendChild(buildVoiceLogItem(item));
    });
    voiceHistoryLoaded = true;
  } catch (err) {
    console.error('Failed to load voice history:', err);
  }
}

function buildVoiceLogItem(item) {
  const el = document.createElement('div');
  el.className = 'voice-log-item';
  el.setAttribute('data-id', item.id);

  const dt = new Date(item.created_at);
  const timeStr = dt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
  const durStr = item.duration_ms ? `${(item.duration_ms / 1000).toFixed(1)}s` : '';
  const srcLabel = item.source === 'upload' ? 'upload' : 'mic';

  el.innerHTML = `
    <svg class="voice-log-icon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
      <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
      <line x1="12" y1="19" x2="12" y2="23"/>
    </svg>
    <div class="voice-log-body">
      <div class="voice-log-preview">${esc(item.text)}</div>
      <div class="voice-log-meta">
        <span class="voice-log-time">${timeStr}</span>
        ${durStr ? `<span class="voice-log-dur">${durStr}</span>` : ''}
        <span class="voice-log-src">${srcLabel}</span>
      </div>
      <div class="voice-log-actions">
        <button class="btn-secondary" onclick="copyVoiceLog(event, ${item.id})">Copy</button>
        <button class="btn-secondary btn-danger" onclick="deleteVoiceLog(event, ${item.id})">Delete</button>
      </div>
    </div>
    <button class="btn-text voice-log-delete" onclick="deleteVoiceLog(event, ${item.id})" title="Delete">&times;</button>
  `;

  el.addEventListener('click', (e) => {
    if (e.target.closest('button')) return;
    el.classList.toggle('expanded');
  });

  return el;
}

async function copyVoiceLog(e, id) {
  e.stopPropagation();
  const item = e.target.closest('.voice-log-item');
  const text = item.querySelector('.voice-log-preview').textContent;
  try { await navigator.clipboard.writeText(text); } catch { document.execCommand('copy'); }
  playSFX('utility');
  const btn = e.target;
  btn.textContent = 'Copied!';
  setTimeout(() => { btn.textContent = 'Copy'; }, 1200);
}

async function deleteVoiceLog(e, id) {
  e.stopPropagation();
  playSFX('delete');
  await fetch(`${API}/voice/history/${id}`, { method: 'DELETE' });
  const item = e.target.closest('.voice-log-item');
  item.remove();
  // Refresh both views
  loadRecentVoice();
  voiceHistoryLoaded = false;
}

// ─── Helpers ────────────────────────────────────────

function esc(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ═══════════════════════════════════════════════════
// NOTES
// ═══════════════════════════════════════════════════

const newNoteBtn = document.getElementById('newNoteBtn');
const noteBackBtn = document.getElementById('noteBackBtn');
const noteSaveBtn = document.getElementById('noteSaveBtn');
const notePinBtn = document.getElementById('notePinBtn');
const noteEnhanceBtn = document.getElementById('noteEnhanceBtn');
const noteDeleteBtn = document.getElementById('noteDeleteBtn');
const noteTitleInput = document.getElementById('noteTitleInput');
const noteContentInput = document.getElementById('noteContentInput');
const noteEditorMeta = document.getElementById('noteEditorMeta');
const noteTabs = document.getElementById('noteTabs');
const tabRaw = document.getElementById('tabRaw');
const tabEnhanced = document.getElementById('tabEnhanced');
const noteEnhancedView = document.getElementById('noteEnhancedView');
const noteEnhancedContent = document.getElementById('noteEnhancedContent');
const staleBanner = document.getElementById('staleBanner');
const notesListView = document.getElementById('notesListView');
const noteEditorView = document.getElementById('noteEditorView');
const notesList = document.getElementById('notesList');
const pinnedNotesList = document.getElementById('pinnedNotesList');
const sendToNoteBtn = document.getElementById('sendToNoteBtn');
let editingNotePinned = false;
let editingHasEnhancement = false;

function hasUnsavedNote() {
  return noteTitleInput.value !== noteSavedTitle || noteContentInput.value !== noteSavedContent;
}

newNoteBtn.addEventListener('click', () => openNoteEditor(null));
noteBackBtn.addEventListener('click', () => {
  if (hasUnsavedNote() && !confirm('You have unsaved changes. Leave without saving?')) return;
  closeNoteEditor();
});
noteSaveBtn.addEventListener('click', saveNote);
noteDeleteBtn.addEventListener('click', deleteNote);
notePinBtn.addEventListener('click', togglePinFromEditor);
noteEnhanceBtn.addEventListener('click', enhanceCurrentNote);

// Voice → Note
sendToNoteBtn.addEventListener('click', async () => {
  const text = resultText.textContent.trim();
  if (!text) return;
  const title = text.slice(0, 60) + (text.length > 60 ? '...' : '');
  await fetch(`${API}/notes/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title, content: text }),
  });
  playSFX('create');
  sendToNoteBtn.textContent = 'Saved!';
  setTimeout(() => { sendToNoteBtn.textContent = 'Add Note'; }, 1500);
});

// Voice → Win
const sendToWinBtn = document.getElementById('sendToWinBtn');
if (sendToWinBtn) {
  sendToWinBtn.addEventListener('click', async () => {
    const text = resultText.textContent.trim();
    if (!text) return;
    await fetch(`${API}/accomplishments/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    playSFX('complete');
    sendToWinBtn.textContent = 'Logged!';
    setTimeout(() => { sendToWinBtn.textContent = 'Log as Win'; }, 1500);
    loadDashboardWins();
  });
}

// ─── Accomplishments / Wins ─────────────────────────
const winInput = document.getElementById('winInput');
const winAddBtn = document.getElementById('winAddBtn');
const winsList = document.getElementById('winsList');
const winsWeekCount = document.getElementById('winsWeekCount');
const winsFilters = document.getElementById('winsFilters');
const dashboardWinsList = document.getElementById('dashboardWinsList');
let winsCache = [];
let winsFilter = 'all';

const SOURCE_LABELS = {
  todo: 'TO-DO',
  question: 'Q&A',
  task: 'TASK',
  manual: 'LOG',
};

async function loadWins() {
  try {
    const resp = await fetch(`${API}/accomplishments/?limit=200`);
    winsCache = await resp.json();
    renderWins();
  } catch (e) {
    winsList.innerHTML = '<p class="empty">Failed to load.</p>';
  }
}

function renderWins() {
  const filtered = winsFilter === 'all'
    ? winsCache
    : winsCache.filter(w => w.source === winsFilter);

  // Week count
  const weekAgo = Date.now() - 7 * 86400000;
  const weekCount = winsCache.filter(w => new Date(w.completed_at).getTime() >= weekAgo).length;
  if (winsWeekCount) {
    winsWeekCount.textContent = `${weekCount} this week`;
    winsWeekCount.style.display = weekCount > 0 ? '' : 'none';
  }

  if (!filtered.length) {
    winsList.innerHTML = '<p class="empty">Nothing here yet.</p>';
    return;
  }

  // Group by day
  const groups = {};
  const order = [];
  for (const w of filtered) {
    const d = new Date(w.completed_at);
    const key = d.toDateString();
    if (!(key in groups)) { groups[key] = []; order.push(key); }
    groups[key].push(w);
  }

  const today = new Date().toDateString();
  const yesterday = new Date(Date.now() - 86400000).toDateString();

  let html = '';
  for (const key of order) {
    let label = key;
    if (key === today) label = 'TODAY';
    else if (key === yesterday) label = 'YESTERDAY';
    else label = new Date(key).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' }).toUpperCase();
    html += `<div class="win-day">${label}</div>`;
    for (const w of groups[key]) {
      const t = new Date(w.completed_at).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
      const pill = `<span class="src-pill src-${esc(w.source)}">${SOURCE_LABELS[w.source] || w.source.toUpperCase()}</span>`;
      html += `
        <div class="win-item">
          <svg class="win-check" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
          <div class="win-text">${esc(w.text)}</div>
          ${pill}
          <div class="win-time">${t}</div>
          <button class="btn-icon win-delete" data-id="${w.id}" title="Delete">&times;</button>
        </div>`;
    }
  }
  winsList.innerHTML = html;

  winsList.querySelectorAll('.win-delete').forEach(b => {
    b.addEventListener('click', async (e) => {
      const id = e.currentTarget.getAttribute('data-id');
      playSFX('delete');
      await fetch(`${API}/accomplishments/${id}`, { method: 'DELETE' });
      loadWins();
      loadDashboardWins();
    });
  });
}

if (winAddBtn) {
  winAddBtn.addEventListener('click', addWin);
  winInput.addEventListener('keydown', e => { if (e.key === 'Enter') addWin(); });
}
async function addWin() {
  const text = winInput.value.trim();
  if (!text) return;
  playSFX('complete');
  await fetch(`${API}/accomplishments/`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  });
  winInput.value = '';
  loadWins();
  loadDashboardWins();
}

if (winsFilters) {
  winsFilters.querySelectorAll('.chip').forEach(c => {
    c.addEventListener('click', () => {
      winsFilters.querySelectorAll('.chip').forEach(x => x.classList.remove('active'));
      c.classList.add('active');
      winsFilter = c.getAttribute('data-source');
      renderWins();
    });
  });
}

async function loadDashboardWins() {
  if (!dashboardWinsList) return;
  try {
    const resp = await fetch(`${API}/accomplishments/?limit=5`);
    const items = await resp.json();
    if (!items.length) {
      dashboardWinsList.innerHTML = '<p class="empty">Quiet on the wire.</p>';
      return;
    }
    let html = '<div class="wins-list">';
    for (const w of items) {
      const t = new Date(w.completed_at);
      const today = new Date().toDateString() === t.toDateString();
      const yesterday = new Date(Date.now() - 86400000).toDateString() === t.toDateString();
      const when = today
        ? t.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })
        : yesterday
          ? 'YESTERDAY'
          : t.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase();
      const pill = `<span class="src-pill src-${esc(w.source)}">${SOURCE_LABELS[w.source] || w.source.toUpperCase()}</span>`;
      html += `
        <div class="win-item">
          <svg class="win-check" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg>
          <div class="win-text">${esc(w.text)}</div>
          ${pill}
          <div class="win-time">${when}</div>
        </div>`;
    }
    html += '</div>';
    dashboardWinsList.innerHTML = html;
  } catch {}
}


function renderNoteItem(n) {
  const preview = (n.content || '').slice(0, 80).replace(/\n/g, ' ');
  const date = new Date(n.updated).toLocaleDateString();
  let enhIndicator = '';
  if (n.pinned && n.has_enhancement) {
    enhIndicator = n.enhancement_stale
      ? '<span class="note-enhanced-indicator stale" title="Enhanced (stale)">&#10024;</span>'
      : '<span class="note-enhanced-indicator fresh" title="Enhanced">&#10024;</span>';
  }
  return `
    <div class="note-item">
      <div class="note-item-info" onclick="openNoteEditor(${n.id})">
        <div class="note-item-title">${esc(n.title)}${enhIndicator}</div>
        <div class="note-item-preview">${esc(preview)}</div>
      </div>
      <div class="note-item-date">${date}</div>
      <button class="note-pin-btn ${n.pinned ? 'pinned' : ''}" onclick="event.stopPropagation();togglePin(${n.id},${n.pinned})" title="${n.pinned ? 'Unpin' : 'Pin'}">
        ${n.pinned ? '\u2605' : '\u2606'}
      </button>
    </div>`;
}

async function loadNotes() {
  try {
    const resp = await fetch(`${API}/notes/`);
    const allNotes = await resp.json();
    const pinned = allNotes.filter(n => n.pinned);
    const unpinned = allNotes.filter(n => !n.pinned);

    notesList.innerHTML = unpinned.length
      ? unpinned.map(renderNoteItem).join('')
      : '<p class="empty">No notes yet.</p>';

    pinnedNotesList.innerHTML = pinned.length
      ? pinned.map(renderNoteItem).join('')
      : '<p class="empty">No pinned notes.</p>';
  } catch {
    notesList.innerHTML = '<p class="empty">Failed to load.</p>';
  }
}

async function togglePin(id, currentlyPinned) {
  if (currentlyPinned) {
    // Double confirm for unpin
    if (!confirm('Unpin this note?')) return;
    if (!confirm('Are you sure you want to unpin?')) return;
    await fetch(`${API}/notes/${id}/unpin`, { method: 'POST' });
  } else {
    await fetch(`${API}/notes/${id}/pin`, { method: 'POST' });
  }
  loadNotes();
}

async function togglePinFromEditor() {
  if (!editingNoteId) return;
  if (editingNotePinned) {
    if (!confirm('Unpin this note?')) return;
    if (!confirm('Are you sure you want to unpin?')) return;
    await fetch(`${API}/notes/${editingNoteId}/unpin`, { method: 'POST' });
    editingNotePinned = false;
  } else {
    await fetch(`${API}/notes/${editingNoteId}/pin`, { method: 'POST' });
    editingNotePinned = true;
  }
  updatePinButton();
}

function updatePinButton() {
  notePinBtn.textContent = editingNotePinned ? 'Unpin' : 'Pin';
  notePinBtn.className = editingNotePinned ? 'btn-secondary' : 'btn-secondary';
}

async function openNoteEditor(id) {
  editingNoteId = id;
  notesListView.style.display = 'none';
  noteEditorView.style.display = 'block';

  // Reset to raw tab
  switchNoteTab('raw');

  if (id) {
    noteDeleteBtn.style.display = 'inline-block';
    notePinBtn.style.display = 'inline-block';
    try {
      const resp = await fetch(`${API}/notes/${id}`);
      const note = await resp.json();
      noteTitleInput.value = note.title;
      noteContentInput.value = note.content;
      noteSavedTitle = note.title;
      noteSavedContent = note.content;
      editingNotePinned = note.pinned;
      editingHasEnhancement = note.has_enhancement;
      updatePinButton();

      // Show enhance button and tabs for pinned notes
      noteEnhanceBtn.style.display = note.pinned ? 'inline-block' : 'none';
      noteTabs.style.display = (note.pinned && note.has_enhancement) ? 'flex' : 'none';

      const created = new Date(note.created).toLocaleString();
      const updated = new Date(note.updated).toLocaleString();
      noteEditorMeta.textContent = `Created: ${created} · Updated: ${updated}`;
    } catch {
      noteTitleInput.value = '';
      noteContentInput.value = '';
      noteEditorMeta.textContent = '';
    }
  } else {
    noteDeleteBtn.style.display = 'none';
    notePinBtn.style.display = 'none';
    noteEnhanceBtn.style.display = 'none';
    noteTabs.style.display = 'none';
    noteTitleInput.value = '';
    noteContentInput.value = '';
    noteSavedTitle = '';
    noteSavedContent = '';
    editingNotePinned = false;
    editingHasEnhancement = false;
    noteEditorMeta.textContent = '';
  }
  noteTitleInput.focus();
}

function closeNoteEditor() {
  noteEditorView.style.display = 'none';
  notesListView.style.display = 'block';
  editingNoteId = null;
  loadNotes();
}

async function saveNote() {
  const title = noteTitleInput.value.trim();
  const content = noteContentInput.value;
  if (!title) { noteTitleInput.focus(); return; }

  noteSaveBtn.disabled = true;
  try {
    if (editingNoteId) {
      await fetch(`${API}/notes/${editingNoteId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content }),
      });
    } else {
      const resp = await fetch(`${API}/notes/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, content }),
      });
      const note = await resp.json();
      editingNoteId = note.id;
      noteDeleteBtn.style.display = 'inline-block';
      notePinBtn.style.display = 'inline-block';
    }
    noteSavedTitle = title;
    noteSavedContent = content;
    playSFX('create');
    noteSaveBtn.textContent = 'Saved!';
    setTimeout(() => { noteSaveBtn.textContent = 'Save'; }, 1500);
  } catch {}
  noteSaveBtn.disabled = false;
}

async function deleteNote() {
  if (!editingNoteId) return;
  playSFX('delete');
  await fetch(`${API}/notes/${editingNoteId}`, { method: 'DELETE' });
  closeNoteEditor();
}

// ─── Note Enhancement ───────────────────────────────

function switchNoteTab(tab) {
  if (tab === 'raw') {
    tabRaw.classList.add('active');
    tabEnhanced.classList.remove('active');
    noteContentInput.style.display = 'block';
    noteEnhancedView.style.display = 'none';
  } else {
    tabRaw.classList.remove('active');
    tabEnhanced.classList.add('active');
    noteContentInput.style.display = 'none';
    noteEnhancedView.style.display = 'block';
    loadEnhancedView();
  }
}

async function loadEnhancedView() {
  if (!editingNoteId) return;
  noteEnhancedContent.innerHTML = '<div class="processing"><div class="spinner"></div><span>Loading...</span></div>';
  staleBanner.style.display = 'none';
  document.getElementById('answersBanner').style.display = 'none';

  try {
    const resp = await fetch(`${API}/notes/${editingNoteId}/enhancement`);
    const data = await resp.json();
    if (data.error) {
      noteEnhancedContent.innerHTML = '<p class="empty">No enhancement yet. Click "Enhance" to generate one.</p>';
      return;
    }
    if (data.stale) {
      staleBanner.style.display = 'block';
    }
    if (data.answered_question_count > 0) {
      const banner = document.getElementById('answersBanner');
      const n = data.answered_question_count;
      document.getElementById('answersBannerText').textContent =
        `${n} answered question${n > 1 ? 's' : ''} available to incorporate.`;
      banner.style.display = 'block';
    }
    noteEnhancedContent.innerHTML = marked.parse(data.enhanced_content);
  } catch {
    noteEnhancedContent.innerHTML = '<p class="empty">Failed to load enhancement.</p>';
  }
}

async function enhanceCurrentNote() {
  if (!editingNoteId) return;

  // Save first if there are unsaved changes
  if (hasUnsavedNote()) {
    await saveNote();
  }

  noteEnhanceBtn.disabled = true;
  noteEnhanceBtn.innerHTML = '<span class="enhance-spinner"><div class="spinner" style="width:12px;height:12px;border-width:2px;"></div> Enhancing...</span>';

  try {
    const resp = await fetch(`${API}/notes/${editingNoteId}/enhance`, { method: 'POST' });
    const data = await resp.json();

    if (data.error) {
      alert(data.error);
    } else {
      playSFX('epic');
      editingHasEnhancement = true;
      noteTabs.style.display = 'flex';
      switchNoteTab('enhanced');
      // Refresh dashboard in case clarification questions were created
      if (data.clarifications_created > 0) {
        loadDashboardAttention();
      }
    }
  } catch (err) {
    alert('Enhancement failed: ' + err.message);
  }

  noteEnhanceBtn.disabled = false;
  noteEnhanceBtn.textContent = 'Enhance';
}

// Guard browser close/refresh
window.addEventListener('beforeunload', (e) => {
  if (noteEditorView.style.display !== 'none' && hasUnsavedNote()) {
    e.preventDefault();
  }
});

// ─── Kanban ────────────────────────────────────────

let currentBoard = 'tech';

async function loadBoard(boardName) {
  currentBoard = boardName;

  // Update tab active state
  document.querySelectorAll('.board-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.board-tab').forEach(t => {
    if (t.textContent.toLowerCase().replace(' ', '') === boardName.replace('_', ''))
      t.classList.add('active');
  });
  // Fix matching for multi-word boards
  const tabMap = { tech: 'Tech', house: 'House', gamedev: 'Game Dev', personal: 'Personal' };
  document.querySelectorAll('.board-tab').forEach(t => {
    t.classList.toggle('active', t.textContent === tabMap[boardName]);
  });

  const container = document.getElementById('kanbanBoard');
  try {
    const resp = await fetch(`${API}/kanban/boards/${boardName}`);
    const data = await resp.json();
    if (data.error) { container.innerHTML = `<p class="empty">${esc(data.error)}</p>`; return; }

    const colOrder = ['backlog', 'in_progress', 'review', 'done'];
    container.innerHTML = colOrder.map(col => {
      const cards = data.columns[col] || [];
      const label = data.column_labels[col];
      return `
        <div class="kanban-col" data-col="${col}"
             ondragover="event.preventDefault(); this.classList.add('drag-over')"
             ondragleave="this.classList.remove('drag-over')"
             ondrop="dropCard(event, '${col}'); this.classList.remove('drag-over')">
          <div class="kanban-col-header">
            <span>${label}</span>
            <span class="kanban-col-count">${cards.length}</span>
          </div>
          <div class="kanban-cards">
            ${cards.map(c => renderKanbanCard(c)).join('')}
          </div>
          <div class="kanban-add">
            <input type="text" class="kanban-add-input" id="kanban-add-${col}" placeholder="+ Add card" autocomplete="off"
                   onkeydown="if(event.key==='Enter')addKanbanCard('${col}', this.value)">
          </div>
        </div>`;
    }).join('');
  } catch {
    container.innerHTML = '<p class="empty">Failed to load board.</p>';
  }
}

function renderKanbanCard(card) {
  const staleClass = card.col === 'in_progress' && card.age_days >= 14 ? ' kanban-card-stale' : '';
  const colorStyle = card.color ? ` style="border-left: 3px solid ${card.color}"` : '';
  const age = card.age_days > 0 ? `<span class="kanban-card-age">${card.age_days}d</span>` : '';
  const project = card.project ? `<span class="tag project">${esc(card.project)}</span>` : '';
  return `
    <div class="kanban-card${staleClass}" draggable="true" data-id="${card.id}"${colorStyle}
         ondragstart="event.dataTransfer.setData('text/plain', '${card.id}')">
      <div class="kanban-card-title">${esc(card.title)}</div>
      <div class="kanban-card-meta">${project}${age}</div>
      <button class="kanban-card-delete" onclick="deleteKanbanCard(${card.id})" title="Delete">&times;</button>
    </div>`;
}

async function addKanbanCard(column, title) {
  title = title.trim();
  if (!title) return;
  playSFX('create');
  await fetch(`${API}/kanban/cards`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ board: currentBoard, title, column }),
  });
  loadBoard(currentBoard);
}

async function dropCard(event, newColumn) {
  event.preventDefault();
  const cardId = event.dataTransfer.getData('text/plain');
  if (!cardId) return;
  playSFX('utility');
  await fetch(`${API}/kanban/cards/${cardId}/move`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ column: newColumn }),
  });
  loadBoard(currentBoard);
}

async function deleteKanbanCard(id) {
  playSFX('delete');
  await fetch(`${API}/kanban/cards/${id}`, { method: 'DELETE' });
  loadBoard(currentBoard);
}

// ─── Calendar ──────────────────────────────────────

let calPreviewData = null;

async function loadCalendarEvents() {
  const container = document.getElementById('calEventsList');
  try {
    const resp = await fetch(`${API}/calendar/upcoming`);
    const events = await resp.json();
    if (!events.length) {
      container.innerHTML = '<p class="empty">No upcoming events.</p>';
      return;
    }
    container.innerHTML = events.map(e => {
      const start = new Date(e.start_time);
      const end = new Date(e.end_time);
      const dateStr = start.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
      const timeStr = start.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) + ' - ' +
                      end.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      const attendees = e.attendees ? `<div class="cal-attendees">${esc(e.attendees)}</div>` : '';
      const location = e.location ? `<div class="cal-location">${esc(e.location)}</div>` : '';
      const deleteBtn = e.id ? `<button class="todo-delete" style="opacity:1" onclick="cancelCalEvent(${e.id})" title="Cancel">&times;</button>` : '';
      return `
        <div class="cal-event">
          <div class="cal-event-info">
            <div class="cal-event-title">${esc(e.summary)}</div>
            <div class="cal-event-time">${dateStr} &middot; ${timeStr}</div>
            ${location}${attendees}
          </div>
          ${deleteBtn}
        </div>`;
    }).join('');
  } catch {
    container.innerHTML = '<p class="empty">Failed to load events.</p>';
  }
}

function showCalPreview(data) {
  calPreviewData = data;
  const card = document.getElementById('calPreviewCard');
  document.getElementById('calPreviewTitle').value = data.summary || '';
  // Format for datetime-local input
  const fmtDT = (iso) => iso ? iso.substring(0, 16) : '';
  document.getElementById('calPreviewStart').value = fmtDT(data.start_time);
  document.getElementById('calPreviewEnd').value = fmtDT(data.end_time);
  document.getElementById('calPreviewLocation').value = data.location || '';
  document.getElementById('calPreviewAttendees').value = data.attendees || '';
  document.getElementById('calPreviewDesc').value = data.description || '';
  card.style.display = 'block';
  card.scrollIntoView({ behavior: 'smooth' });
}

// Parse natural language
document.getElementById('calParseBtn').addEventListener('click', async () => {
  const text = document.getElementById('calSmartInput').value.trim();
  if (!text) return;

  const btn = document.getElementById('calParseBtn');
  btn.disabled = true; btn.textContent = 'Parsing...';

  try {
    const resp = await fetch(`${API}/calendar/parse`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
    const data = await resp.json();
    if (data.success) {
      showCalPreview(data);
      document.getElementById('calSmartInput').value = '';
    } else {
      alert(data.error || 'Failed to parse event');
    }
  } catch (err) {
    alert('Parse failed: ' + err.message);
  }

  btn.disabled = false; btn.textContent = 'Parse Event';
});

// Parse image
document.getElementById('calImageInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;

  const form = new FormData();
  form.append('file', file);

  // Show loading
  const label = document.querySelector('label[for="calImageInput"]') || e.target.parentElement;
  const origHTML = label.innerHTML;
  label.innerHTML = '<div class="spinner" style="width:12px;height:12px;border-width:2px;display:inline-block"></div> Parsing...';

  try {
    const resp = await fetch(`${API}/calendar/parse-image`, { method: 'POST', body: form });
    const data = await resp.json();
    if (data.success) {
      showCalPreview(data);
    } else {
      alert(data.error || 'Failed to parse image');
    }
  } catch (err) {
    alert('Image parse failed: ' + err.message);
  }

  label.innerHTML = origHTML;
  e.target.value = '';
});

// Confirm parsed event
document.getElementById('calConfirmBtn').addEventListener('click', async () => {
  const btn = document.getElementById('calConfirmBtn');
  btn.disabled = true; btn.textContent = 'Creating...';

  const start = document.getElementById('calPreviewStart').value;
  const end = document.getElementById('calPreviewEnd').value;

  await fetch(`${API}/calendar/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      summary: document.getElementById('calPreviewTitle').value,
      start_time: start ? start + ':00' : '',
      end_time: end ? end + ':00' : '',
      location: document.getElementById('calPreviewLocation').value,
      attendees: document.getElementById('calPreviewAttendees').value,
      description: document.getElementById('calPreviewDesc').value,
    }),
  });

  playSFX('create');
  document.getElementById('calPreviewCard').style.display = 'none';
  btn.disabled = false; btn.textContent = 'Create Event';
  loadCalendarEvents();
});

// Preview as hold
document.getElementById('calPreviewHoldBtn').addEventListener('click', async () => {
  const btn = document.getElementById('calPreviewHoldBtn');
  btn.disabled = true; btn.textContent = 'Creating...';

  const start = document.getElementById('calPreviewStart').value;
  const end = document.getElementById('calPreviewEnd').value;

  await fetch(`${API}/calendar/hold`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      summary: document.getElementById('calPreviewTitle').value,
      start_time: start ? start + ':00' : '',
      end_time: end ? end + ':00' : '',
      description: document.getElementById('calPreviewDesc').value,
    }),
  });

  playSFX('create');
  document.getElementById('calPreviewCard').style.display = 'none';
  btn.disabled = false; btn.textContent = 'As Hold';
  loadCalendarEvents();
});

// Cancel preview
document.getElementById('calPreviewCancel').addEventListener('click', () => {
  document.getElementById('calPreviewCard').style.display = 'none';
});

// Manual entry toggle
document.getElementById('calManualToggle').addEventListener('click', () => {
  const card = document.getElementById('calManualCard');
  card.style.display = card.style.display === 'none' ? 'block' : 'none';
});

// Manual create
document.getElementById('calCreateBtn').addEventListener('click', async () => {
  const summary = document.getElementById('calSummary').value.trim();
  const start = document.getElementById('calStart').value;
  const end = document.getElementById('calEnd').value;
  if (!summary || !start || !end) { alert('Title, start, and end are required.'); return; }

  const btn = document.getElementById('calCreateBtn');
  btn.disabled = true; btn.textContent = 'Creating...';

  await fetch(`${API}/calendar/events`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      summary,
      start_time: start + ':00',
      end_time: end + ':00',
      description: document.getElementById('calDescription').value.trim(),
      attendees: document.getElementById('calAttendees').value.trim(),
      location: document.getElementById('calLocation').value.trim(),
    }),
  });

  playSFX('create');
  document.getElementById('calSummary').value = '';
  document.getElementById('calStart').value = '';
  document.getElementById('calEnd').value = '';
  document.getElementById('calDescription').value = '';
  document.getElementById('calAttendees').value = '';
  document.getElementById('calLocation').value = '';
  btn.disabled = false; btn.textContent = 'Create Event';
  document.getElementById('calManualCard').style.display = 'none';
  loadCalendarEvents();
});

// Manual hold
document.getElementById('calHoldBtn').addEventListener('click', async () => {
  const summary = document.getElementById('calSummary').value.trim();
  const start = document.getElementById('calStart').value;
  const end = document.getElementById('calEnd').value;
  if (!summary || !start || !end) { alert('Title, start, and end are required.'); return; }

  const btn = document.getElementById('calHoldBtn');
  btn.disabled = true; btn.textContent = 'Creating...';

  await fetch(`${API}/calendar/hold`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      summary,
      start_time: start + ':00',
      end_time: end + ':00',
      description: document.getElementById('calDescription').value.trim(),
    }),
  });

  document.getElementById('calSummary').value = '';
  document.getElementById('calStart').value = '';
  document.getElementById('calEnd').value = '';
  document.getElementById('calDescription').value = '';
  btn.disabled = false; btn.textContent = 'Calendar Hold';
  document.getElementById('calManualCard').style.display = 'none';
  loadCalendarEvents();
});

async function cancelCalEvent(id) {
  if (!confirm('Cancel this event? Attendees will be notified.')) return;
  playSFX('delete');
  await fetch(`${API}/calendar/events/${id}`, { method: 'DELETE' });
  loadCalendarEvents();
}

document.getElementById('calRefreshBtn').addEventListener('click', loadCalendarEvents);

// ─── Contacts ──────────────────────────────────────

async function loadContacts() {
  try {
    const resp = await fetch(`${API}/calendar/contacts`);
    const contacts = await resp.json();
    const container = document.getElementById('contactsList');
    if (!contacts.length) {
      container.innerHTML = '<p class="empty" style="padding:0.5rem 0">No contacts saved.</p>';
      return;
    }
    container.innerHTML = contacts.map(c => `
      <span class="contact-chip" onclick="addContactToAttendees('${esc(c.email)}')" title="Click to add as attendee">
        <span class="contact-name">${esc(c.name)}</span>
        <span class="contact-email">${esc(c.email)}</span>
        <button class="contact-delete" onclick="event.stopPropagation(); deleteContact(${c.id})" title="Remove">&times;</button>
      </span>
    `).join('');
  } catch {
    document.getElementById('contactsList').innerHTML = '';
  }
}

function addContactToAttendees(email) {
  // Find the visible attendees input (preview or manual)
  const previewCard = document.getElementById('calPreviewCard');
  const manualCard = document.getElementById('calManualCard');
  let input;
  if (previewCard.style.display !== 'none') {
    input = document.getElementById('calPreviewAttendees');
  } else if (manualCard.style.display !== 'none') {
    input = document.getElementById('calAttendees');
  } else {
    // No form visible — open manual entry and use that
    document.getElementById('calManualCard').style.display = 'block';
    input = document.getElementById('calAttendees');
  }

  const current = input.value.trim();
  if (current && !current.split(',').map(e => e.trim()).includes(email)) {
    input.value = current + ', ' + email;
  } else if (!current) {
    input.value = email;
  }
}

document.getElementById('contactAddBtn').addEventListener('click', async () => {
  const name = document.getElementById('contactName').value.trim();
  const email = document.getElementById('contactEmail').value.trim();
  if (!name || !email) return;

  await fetch(`${API}/calendar/contacts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email }),
  });

  document.getElementById('contactName').value = '';
  document.getElementById('contactEmail').value = '';
  loadContacts();
});

async function deleteContact(id) {
  await fetch(`${API}/calendar/contacts/${id}`, { method: 'DELETE' });
  loadContacts();
}

// ─── Briefing ──────────────────────────────────────

async function loadBriefing() {
  const content = document.getElementById('briefingContent');
  const timeEl = document.getElementById('briefingTime');

  try {
    const resp = await fetch(`${API}/briefing/`);
    const data = await resp.json();

    if (data.summary) {
      content.innerHTML = marked.parse(data.summary);
      const genDate = new Date(data.generated_at);
      timeEl.textContent = genDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else {
      content.innerHTML = '<p class="empty">No briefing data available.</p>';
    }
  } catch {
    content.innerHTML = '<p class="empty">Failed to load briefing.</p>';
  }
}

document.getElementById('briefingRefreshBtn').addEventListener('click', async () => {
  const btn = document.getElementById('briefingRefreshBtn');
  const content = document.getElementById('briefingContent');
  btn.disabled = true;
  btn.textContent = 'Generating...';
  content.innerHTML = '<div class="processing"><div class="spinner"></div><span>Generating briefing...</span></div>';

  try {
    const resp = await fetch(`${API}/briefing/generate`, { method: 'POST' });
    const data = await resp.json();
    if (data.summary) {
      playSFX('epic');
      content.innerHTML = marked.parse(data.summary);
      const genDate = new Date(data.generated_at);
      document.getElementById('briefingTime').textContent = genDate.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }
  } catch {
    content.innerHTML = '<p class="empty">Failed to generate briefing.</p>';
  }

  btn.disabled = false;
  btn.textContent = 'Refresh';
});

// ─── Settings ──────────────────────────────────────

async function loadSettings() {
  try {
    const resp = await fetch(`${API}/settings/`);
    const data = await resp.json();

    // Cache SFX values so playSFX() reflects current preferences immediately
    if (data.sfx_enabled) PAM_SETTINGS.sfx_enabled = !!data.sfx_enabled.value;
    if (data.sfx_volume) PAM_SETTINGS.sfx_volume = Number(data.sfx_volume.value);

    document.querySelectorAll('.settings-input').forEach(input => {
      const key = input.dataset.setting;
      if (!key || !(key in data)) return;
      const val = data[key].value;
      if (input.type === 'checkbox') {
        input.checked = !!val;
      } else {
        input.value = val;
      }
    });

    const volLabel = document.getElementById('sfxVolumeLabel');
    if (volLabel) volLabel.textContent = `${Math.round(PAM_SETTINGS.sfx_volume * 100)}%`;
  } catch {
    const status = document.getElementById('settingsStatus');
    if (status) status.textContent = 'Failed to load settings.';
  }
}

async function saveSetting(key, value) {
  try {
    await fetch(`${API}/settings/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key, value }),
    });
    const status = document.getElementById('settingsStatus');
    if (status) {
      status.textContent = `Saved ${key}.`;
      clearTimeout(saveSetting._t);
      saveSetting._t = setTimeout(() => { status.textContent = ''; }, 2000);
    }
  } catch {
    const status = document.getElementById('settingsStatus');
    if (status) status.textContent = `Save failed for ${key}.`;
  }
}

document.querySelectorAll('.settings-input').forEach(input => {
  const key = input.dataset.setting;
  if (!key) return;
  const commit = () => {
    let value;
    if (input.type === 'checkbox') value = input.checked;
    else if (input.type === 'number' || input.type === 'range') value = Number(input.value);
    else value = input.value.trim();

    if (key === 'sfx_enabled') PAM_SETTINGS.sfx_enabled = !!value;
    if (key === 'sfx_volume') {
      PAM_SETTINGS.sfx_volume = Number(value);
      const volLabel = document.getElementById('sfxVolumeLabel');
      if (volLabel) volLabel.textContent = `${Math.round(PAM_SETTINGS.sfx_volume * 100)}%`;
    }
    saveSetting(key, value);
  };
  if (input.type === 'checkbox' || input.type === 'range') {
    input.addEventListener('change', commit);
    if (input.type === 'range') {
      input.addEventListener('input', () => {
        PAM_SETTINGS.sfx_volume = Number(input.value);
        const volLabel = document.getElementById('sfxVolumeLabel');
        if (volLabel) volLabel.textContent = `${Math.round(PAM_SETTINGS.sfx_volume * 100)}%`;
      });
    }
  } else {
    input.addEventListener('change', commit);
    input.addEventListener('blur', commit);
  }
});

// ─── Prompt Zone ───────────────────────────────────

const WAVY_BORDER = `<svg class="golden-wave-svg" viewBox="0 0 100 100" preserveAspectRatio="none"><path class="golden-wave-border" d="M4,0 C15,-2 25,2 36,0 C47,-2 57,2 68,0 C79,-2 89,2 100,0 C100,0 100,0 100,4 C102,15 98,25 100,36 C102,47 98,57 100,68 C102,79 98,89 100,100 C100,100 100,100 96,100 C85,102 75,98 64,100 C53,102 43,98 32,100 C21,102 11,98 0,100 C0,100 0,100 0,96 C-2,85 2,75 0,64 C-2,53 2,43 0,32 C-2,21 2,11 0,0 Z"/></svg>`;

let pzEditingId = null;

async function loadPromptZone() {
  try {
    const resp = await fetch(`${API}/prompts/`);
    const prompts = await resp.json();
    renderGoldenTiles(prompts.filter(p => p.golden));
    renderPromptList(prompts);
  } catch (err) {
    console.error('Failed to load prompts:', err);
  }
}

function renderGoldenTiles(golden) {
  const container = document.getElementById('goldenTiles');
  const countBadge = document.getElementById('goldenCount');
  if (!golden.length) {
    container.innerHTML = '<p class="empty">No golden prompts yet. Star a prompt to make it golden.</p>';
    countBadge.style.display = 'none';
    return;
  }
  countBadge.textContent = golden.length;
  countBadge.style.display = '';
  container.innerHTML = golden.map(p =>
    `<div class="golden-tile" onclick="copyPrompt(${p.id}, this)" title="Click to copy">
      ${WAVY_BORDER}
      <div class="golden-tile-title">${esc(p.title)}</div>
      <div class="golden-tile-text">${esc(p.prompt)}</div>
    </div>`
  ).join('');
}

function renderPromptList(prompts) {
  const container = document.getElementById('pzList');
  const countBadge = document.getElementById('pzTotalCount');
  if (!prompts.length) {
    container.innerHTML = '<p class="empty">No prompts saved yet.</p>';
    countBadge.style.display = 'none';
    return;
  }
  countBadge.textContent = prompts.length;
  countBadge.style.display = '';
  container.innerHTML = prompts.map(p => `
    <div class="pz-item${p.golden ? ' is-golden' : ''}" data-id="${p.id}">
      <div class="pz-item-info">
        <div class="pz-item-title">${esc(p.title)}</div>
        <div class="pz-item-text">${esc(p.prompt)}</div>
      </div>
      <div class="pz-item-actions">
        <button class="pz-star-btn${p.golden ? ' is-golden' : ''}" onclick="toggleGolden(${p.id}, ${p.golden})" title="${p.golden ? 'Remove golden' : 'Make golden'}">${p.golden ? '★' : '☆'}</button>
        <button class="pz-edit-btn" onclick="editPrompt(${p.id})">Edit</button>
        <button class="pz-copy-btn" onclick="copyPrompt(${p.id}, this)">Copy</button>
        <button class="pz-delete-btn" onclick="deletePrompt(${p.id})" title="Delete">&times;</button>
      </div>
    </div>
  `).join('');
}

async function copyPrompt(id, el) {
  try {
    const resp = await fetch(`${API}/prompts/${id}`);
    const data = await resp.json();
    await navigator.clipboard.writeText(data.prompt);
    playSFX('utility');
    el.classList.add('copied');
    setTimeout(() => el.classList.remove('copied'), 1200);
  } catch (e) {
    console.error('Copy failed:', e);
  }
}

async function editPrompt(id) {
  try {
    const resp = await fetch(`${API}/prompts/${id}`);
    const data = await resp.json();
    if (data.error) return;
    pzEditingId = id;
    document.getElementById('pzTitleInput').value = data.title;
    document.getElementById('pzPromptInput').value = data.prompt;
    document.getElementById('pzGoldenInput').checked = data.golden;
    document.getElementById('pzSaveBtn').textContent = 'Update';
    document.querySelector('.pz-add-form').classList.add('pz-form-editing');
    document.getElementById('pzTitleInput').focus();
  } catch (e) {
    console.error('Edit load failed:', e);
  }
}

function cancelEdit() {
  pzEditingId = null;
  document.getElementById('pzTitleInput').value = '';
  document.getElementById('pzPromptInput').value = '';
  document.getElementById('pzGoldenInput').checked = false;
  document.getElementById('pzSaveBtn').textContent = 'Save';
  document.querySelector('.pz-add-form').classList.remove('pz-form-editing');
}

async function toggleGolden(id, currentGolden) {
  playSFX('utility');
  await fetch(`${API}/prompts/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ golden: !currentGolden }),
  });
  loadPromptZone();
}

async function deletePrompt(id) {
  playSFX('delete');
  await fetch(`${API}/prompts/${id}`, { method: 'DELETE' });
  if (pzEditingId === id) cancelEdit();
  loadPromptZone();
}

document.getElementById('pzSaveBtn').addEventListener('click', async () => {
  const title = document.getElementById('pzTitleInput').value.trim();
  const prompt = document.getElementById('pzPromptInput').value.trim();
  const golden = document.getElementById('pzGoldenInput').checked;
  if (!title || !prompt) return;

  if (pzEditingId) {
    await fetch(`${API}/prompts/${pzEditingId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, prompt, golden }),
    });
  } else {
    await fetch(`${API}/prompts/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, prompt, golden }),
    });
  }

  playSFX('create');
  cancelEdit();
  loadPromptZone();
});

document.getElementById('pzCancelBtn').addEventListener('click', cancelEdit);

// ─── Init ───────────────────────────────────────────

checkWhisperStatus();
setInterval(checkWhisperStatus, 30000);
loadBriefing();
loadCalendarEvents();
loadContacts();
loadTodos();
loadDashboardAttention();
loadNotes();
loadSettings();
loadDashboardWins();
loadDashboardHabits();

// ─── Habits ─────────────────────────────────────

const RECURRENCE_LABELS = { daily: 'Daily', weekdays: 'Weekdays', MWF: 'MWF', TTh: 'TTh', weekly: 'Weekly', custom: 'Custom' };

async function loadDashboardHabits() {
  const widget = document.getElementById('habitsWidget');
  const badge = document.getElementById('habitProgress');
  try {
    const resp = await fetch(`${API}/todos/habits/summary`);
    const data = await resp.json();
    const habits = data.habits || [];
    if (!habits.length) {
      widget.innerHTML = '<p class="empty">No habits yet. <a href="#" onclick="showSection(\'habits\'); return false;">Add one</a></p>';
      badge.style.display = 'none';
      return;
    }
    badge.textContent = `${data.today_done}/${data.today_total}`;
    badge.style.display = '';
    widget.innerHTML = habits.map(h => {
      const exp = h.expected_per_week || 7;
      const wk = h.week_count || 0;
      return `
      <div class="habit-widget-item ${h.done ? 'habit-done-today' : ''}">
        <span class="habit-name ${h.done ? 'done' : ''}">${esc(h.text)}</span>
        <span class="habit-week" title="Times completed this week">${wk}/${exp}</span>
        <button class="habit-didit ${h.done ? 'done' : ''}"
                onclick="tapHabit('${h.id}', ${h.done})"
                title="${h.done ? 'Tap to undo today' : 'Mark done for today'}">
          ${h.done ? '✓ Done' : 'Did it'}
        </button>
      </div>
    `;
    }).join('');
  } catch (err) {
    console.error('Failed to load habits widget:', err);
  }
}

async function tapHabit(id, wasDone) {
  try {
    await fetch(`${API}/todos/${id}/toggle`, { method: 'POST' });
    if (!wasDone) playSFX('complete');
    loadDashboardHabits();
    if (!document.getElementById('page-habits').classList.contains('hidden')) loadHabitsPage();
    setTimeout(() => loadDashboardWins(), 200);
  } catch (err) {
    console.error('Failed to tap habit:', err);
  }
}

async function toggleHabit(id, wasDone) {
  try {
    await fetch(`${API}/todos/${id}/toggle`, { method: 'POST' });
    if (!wasDone) playSFX('complete');
    loadDashboardHabits();
    // Also refresh habits page if visible
    if (!document.getElementById('page-habits').classList.contains('hidden')) loadHabitsPage();
    setTimeout(() => loadDashboardWins(), 200);
  } catch (err) {
    console.error('Failed to toggle habit:', err);
  }
}

async function loadHabitsPage() {
  const list = document.getElementById('habitsPageList');
  const badge = document.getElementById('habitPageProgress');
  const fill = document.getElementById('habitsProgressFill');
  try {
    const resp = await fetch(`${API}/todos/habits`);
    const habits = await resp.json();
    if (!habits.length) {
      list.innerHTML = '<p class="empty">No habits yet. Add your first one below.</p>';
      badge.style.display = 'none';
      fill.style.width = '0%';
      return;
    }
    const total = habits.length;
    const done = habits.filter(h => h.done).length;
    badge.textContent = `${done}/${total}`;
    badge.style.display = '';
    const pct = total > 0 ? Math.round((done / total) * 100) : 0;
    fill.style.width = `${pct}%`;

    list.innerHTML = habits.map(h => {
      const exp = h.expected_per_week || 7;
      const wk = h.week_count || 0;
      const total = h.completion_count || 0;
      return `
      <div class="habit-card ${h.done ? 'habit-done' : ''}">
        <label class="habit-check">
          <input type="checkbox" ${h.done ? 'checked' : ''} onchange="toggleHabit('${h.id}', ${h.done})">
          <span class="habit-name ${h.done ? 'done' : ''}">${esc(h.text)}</span>
        </label>
        <div class="habit-meta">
          <span class="habit-recurrence-badge">${RECURRENCE_LABELS[h.recurrence] || h.recurrence}</span>
          <span class="habit-weekcount" title="This week">${wk}/${exp} this week</span>
          <span class="habit-total" title="All-time completions">${total}× total</span>
          <span class="habit-streak-info">
            ${h.streak_current > 0 ? `🔥 ${h.streak_current}d streak` : ''}
            ${h.streak_best > 0 ? `<span class="habit-best">(best: ${h.streak_best}d)</span>` : ''}
          </span>
          <button class="btn-icon" onclick="deleteHabit('${h.id}')" title="Delete">×</button>
        </div>
      </div>
    `;
    }).join('');
  } catch (err) {
    console.error('Failed to load habits page:', err);
  }
}

async function addHabit() {
  const input = document.getElementById('habitInput');
  const recurrence = document.getElementById('habitRecurrence').value;
  const text = input.value.trim();
  if (!text) return;
  try {
    await fetch(`${API}/todos/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, recurrence }),
    });
    input.value = '';
    playSFX('create');
    loadHabitsPage();
    loadDashboardHabits();
  } catch (err) {
    console.error('Failed to add habit:', err);
  }
}

async function deleteHabit(id) {
  if (!confirm('Delete this habit?')) return;
  try {
    await fetch(`${API}/todos/${id}`, { method: 'DELETE' });
    playSFX('delete');
    loadHabitsPage();
    loadDashboardHabits();
  } catch (err) {
    console.error('Failed to delete habit:', err);
  }
}

// Wire up habit add button + enter key
document.getElementById('habitAddBtn')?.addEventListener('click', addHabit);
document.getElementById('habitInput')?.addEventListener('keydown', e => {
  if (e.key === 'Enter') addHabit();
});


// ─── Gratitude ─────────────────────────────────────

const GRATITUDE_WAVY_BORDER = `<svg class="gratitude-wave-svg" viewBox="0 0 100 100" preserveAspectRatio="none"><path class="gratitude-wave-border" d="M4,0 C15,-2 25,2 36,0 C47,-2 57,2 68,0 C79,-2 89,2 100,0 C100,0 100,0 100,4 C102,15 98,25 100,36 C102,47 98,57 100,68 C102,79 98,89 100,100 C100,100 100,100 96,100 C85,102 75,98 64,100 C53,102 43,98 32,100 C21,102 11,98 0,100 C0,100 0,100 0,96 C-2,85 2,75 0,64 C-2,53 2,43 0,32 C-2,21 2,11 0,0 Z"/></svg>`;

async function loadGratitudePage() {
  const container = document.getElementById('gratitudeTiles');
  try {
    const resp = await fetch(`${API}/gratitude/`);
    const tiles = await resp.json();
    if (!tiles.length) {
      container.innerHTML = '<p class="empty">No gratitude tiles yet.</p>';
      return;
    }
    container.innerHTML = tiles.map(t => {
      const isPillar = t.category === 'pillar';
      const progressHtml = !isPillar && t.progress_data
        ? `<div class="gratitude-progress">${esc(t.progress_data.label || '')}</div>`
        : '';
      const bodyHtml = t.body
        ? `<div class="gratitude-tile-body">${esc(t.body)}</div>`
        : '';
      return `
        <div class="gratitude-tile ${isPillar ? 'gratitude-pillar' : 'gratitude-data'}"
             style="--tile-color: ${t.color}"
             ${isPillar ? `onclick="editGratitudeTile('${t.id}')"` : ''}>
          ${GRATITUDE_WAVY_BORDER}
          <div class="gratitude-tile-icon">${t.icon || ''}</div>
          <div class="gratitude-tile-title">${esc(t.title)}</div>
          ${bodyHtml}
          ${progressHtml}
          ${isPillar ? '<div class="gratitude-tile-hint">click to edit</div>' : ''}
          <button class="gratitude-delete-btn" onclick="event.stopPropagation(); deleteGratitudeTile('${t.id}')" title="Delete">&times;</button>
        </div>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to load gratitude:', err);
  }
}

let editingGratitudeId = null;

async function editGratitudeTile(id) {
  const newBody = prompt('Edit your reflection for this tile:');
  if (newBody === null) return;
  try {
    await fetch(`${API}/gratitude/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ body: newBody }),
    });
    loadGratitudePage();
  } catch (err) {
    console.error('Failed to edit gratitude tile:', err);
  }
}

async function deleteGratitudeTile(id) {
  if (!confirm('Delete this gratitude tile?')) return;
  try {
    await fetch(`${API}/gratitude/${id}`, { method: 'DELETE' });
    playSFX('delete');
    loadGratitudePage();
  } catch (err) {
    console.error('Failed to delete gratitude tile:', err);
  }
}

async function addGratitudeTile() {
  const title = document.getElementById('gratitudeTitleInput').value.trim();
  const body = document.getElementById('gratitudeBodyInput').value.trim();
  const icon = document.getElementById('gratitudeIconInput').value.trim();
  const color = document.getElementById('gratitudeColorSelect').value;
  if (!title) return;
  try {
    await fetch(`${API}/gratitude/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, body, icon, category: 'pillar', color }),
    });
    document.getElementById('gratitudeTitleInput').value = '';
    document.getElementById('gratitudeBodyInput').value = '';
    document.getElementById('gratitudeIconInput').value = '';
    document.getElementById('addGratitudeForm').style.display = 'none';
    playSFX('create');
    loadGratitudePage();
  } catch (err) {
    console.error('Failed to add gratitude tile:', err);
  }
}

// Wire up gratitude buttons
document.getElementById('addGratitudeTileBtn')?.addEventListener('click', () => {
  const form = document.getElementById('addGratitudeForm');
  form.style.display = form.style.display === 'none' ? 'block' : 'none';
});
document.getElementById('gratitudeSaveBtn')?.addEventListener('click', addGratitudeTile);
document.getElementById('gratitudeCancelBtn')?.addEventListener('click', () => {
  document.getElementById('addGratitudeForm').style.display = 'none';
});

// PAM ambient presence — time-of-day portrait rotation, click to cycle within bucket
(function() {
  const presence = document.getElementById('pamPresence');
  const img = document.getElementById('pamPresenceImg');
  const txt = document.getElementById('pamPresenceText');
  const tm  = document.getElementById('pamPresenceTime');
  if (!presence || !img) return;

  let buckets = { morning: [], workday: [], evening: [] };
  let activeList = ['/img/pam2.png'];
  let cur = 0;
  let currentPeriod = null;

  function periodFor(h) {
    if (h >= 6 && h < 8)   return 'morning';
    if (h >= 8 && h < 20)  return 'workday';
    return 'evening'; // 20-06
  }

  function statusFor(h) {
    if (h < 6)  return 'On call';
    if (h < 8)  return 'Good morning';
    if (h < 12) return 'On duty';
    if (h < 14) return 'Midday';
    if (h < 18) return 'Still working';
    if (h < 20) return 'Wrapping up';
    if (h < 24) return 'After hours';
    return 'On call';
  }

  function refreshPortrait(force) {
    const d = new Date();
    const period = periodFor(d.getHours());
    if (force || period !== currentPeriod) {
      currentPeriod = period;
      const list = (buckets[period] && buckets[period].length) ? buckets[period] : null;
      if (list) {
        activeList = list;
        // Deterministic pick per (day, period) so it doesn't churn on every tick
        const dayIdx = Math.floor(Date.now() / 86400000);
        cur = (dayIdx + period.length) % activeList.length;
        img.src = activeList[cur];
      }
    }
  }

  function tick() {
    const d = new Date();
    txt.textContent = statusFor(d.getHours());
    tm.textContent  = d.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' });
    refreshPortrait(false);
  }

  // Load buckets, then start
  fetch(`${API}/portraits`)
    .then(r => r.json())
    .then(data => {
      buckets = data || buckets;
      refreshPortrait(true);
    })
    .catch(() => {})
    .finally(tick);
  setInterval(tick, 30000);

  presence.addEventListener('click', () => {
    if (activeList.length < 2) return;
    cur = (cur + 1) % activeList.length;
    img.style.opacity = '0';
    setTimeout(() => {
      img.src = activeList[cur];
      img.style.opacity = '1';
    }, 200);
  });
})();
