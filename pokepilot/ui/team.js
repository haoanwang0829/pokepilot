// 类型名称到编号的映射（对应 sprites/sprites/types/generation-ix/scarlet-violet/small/*.png）
const TYPE_ID_MAP = {
    'Normal': 1,
    'Fighting': 2,
    'Flying': 3,
    'Poison': 4,
    'Ground': 5,
    'Rock': 6,
    'Bug': 7,
    'Ghost': 8,
    'Steel': 9,
    'Fire': 10,
    'Water': 11,
    'Grass': 12,
    'Electric': 13,
    'Psychic': 14,
    'Ice': 15,
    'Dragon': 16,
    'Dark': 17,
    'Fairy': 18
};

// 全局队伍数据
let currentTeams = { 'my-team': [], 'opp-team': [] };
let oppTeamVariants = null;
let oppTeamVariantIndex = 0;
// 虚化状态
let fadedElements = { my: new Set(), opp: new Set() };
// 对方速度图标拖拽位置（0~1，表示在范围内的相对位置）
let oppSpeedMarkerRatio = {};
let oppSpeedDragState = null;
// 速度轴配置
const MIN_SPEED = 50;
const BASE_MAX_SPEED = 200;
const MAX_SPEED_STEP = 10;
const AXIS_MAJOR_STEP = 50;
// 场地状态
let speedFieldState = {
    my_tailwind: false,
    opp_tailwind: false,
    my_friendGuard: false,
    my_lightScreen: false,
    my_reflect: false,
    my_auroraVeil: false,
    opp_friendGuard: false,
    opp_lightScreen: false,
    opp_reflect: false,
    opp_auroraVeil: false,
    weather: null,
    terrain: null
};
// 能力等级状态：每个宝可梦独立存储，以图鉴编号为key
let boostState = {
    my: {},
    opp: {}
};
function getBoosts(side, index) {
    const key = (side === 'my-team' || side === 'my') ? 'my' : 'opp';
    return boostState[key][index] || { atk: 0, def: 0, spa: 0, spd: 0, spe: 0 };
}
let moveDamageDragState = null;
let battleMode = 'double';
let activeDamageQuery = null;

// 性格对速度的倍率映射
const SPEED_UP_NATURES = ["timid", "hasty", "jolly", "naive"];
const SPEED_DOWN_NATURES = ["brave", "relaxed", "quiet", "sassy"];

function getNatureSpeedMultiplier(natureList) {
    if (!natureList || natureList.length === 0) return 1.0;
    const top = natureList[0];
    const name = (top.name || top).toLowerCase();
    if (SPEED_UP_NATURES.includes(name)) return 1.1;
    if (SPEED_DOWN_NATURES.includes(name)) return 0.9;
    return 1.0;
}


function isChoiceScarf(pokemon) {
    if (pokemon?.item && pokemon.item.toLowerCase().replace(/[-\s]/g, '').includes('choicescarf')) return true;
    const first = Array.isArray(pokemon?.held_item) ? pokemon.held_item[0] : pokemon?.held_item;
    if (first && typeof first === 'object') {
        const name = (first.name || '').toLowerCase().replace(/[-\s]/g, '');
        const nameZh = first.name_zh || '';
        return name.includes('choicescarf') || nameZh.includes('讲究围巾');
    }
    return false;
}

function getEffectiveSpeed(speed, hasTailwind, isScarf = false, speedBoost = 0) {
    let value = Number(speed) || 0;
    // 能力等级修正：+1=1.5x, +2=2x, +3=2.5x, +4=3x, +5=3.5x, +6=4x
    // -1=2/3, -2=0.5, -3=0.4, -4=1/3, -5=2/7, -6=0.25
    if (speedBoost > 0) {
        value = Math.floor(value * (2 + speedBoost) / 2);
    } else if (speedBoost < 0) {
        value = Math.floor(value * 2 / (2 - speedBoost));
    }
    if (hasTailwind) value *= 2;
    if (isScarf) value *= 1.5;
    return Math.floor(value);
}


function getDynamicMaxSpeed() {
    const maxCandidates = [];

    (currentTeams['my-team'] || []).forEach((pokemon, i) => {
        const speed = pokemon?.stats?.speed;
        const spdBoost = (boostState.my[pokemon.index] || {}).spe || 0;
        maxCandidates.push(getEffectiveSpeed(speed, speedFieldState.my_tailwind, isChoiceScarf(pokemon), spdBoost));
    });

    (currentTeams['opp-team'] || []).forEach((pokemon, i) => {
        const speed = pokemon?.stats?.speed;
        const spdBoost = (boostState.opp[pokemon.index] || {}).spe || 0;
        if (Array.isArray(speed)) {
            maxCandidates.push(getEffectiveSpeed(speed[0], speedFieldState.opp_tailwind, isChoiceScarf(pokemon), spdBoost));
            maxCandidates.push(getEffectiveSpeed(speed[1], speedFieldState.opp_tailwind, isChoiceScarf(pokemon), spdBoost));
        } else {
            maxCandidates.push(getEffectiveSpeed(speed, speedFieldState.opp_tailwind, isChoiceScarf(pokemon), spdBoost));
        }
    });

    const currentMaxSpeed = Math.max(BASE_MAX_SPEED, ...maxCandidates);
    return Math.ceil(currentMaxSpeed / MAX_SPEED_STEP) * MAX_SPEED_STEP;
}


function speedToPercent(speed, maxSpeed) {
    if (maxSpeed <= MIN_SPEED) return 0;
    const ratio = (speed - MIN_SPEED) / (maxSpeed - MIN_SPEED);
    return Math.max(0, Math.min(ratio * 100, 100));
}


function updateTailwindButtons() {
    const myTailwindButton = document.getElementById('btn-tailwind-my');
    const oppTailwindButton = document.getElementById('btn-tailwind-opp');
    if (myTailwindButton) myTailwindButton.classList.toggle('active', speedFieldState.my_tailwind);
    if (oppTailwindButton) oppTailwindButton.classList.toggle('active', speedFieldState.opp_tailwind);
}


function toggleTailwind(side) {
    if (side === 'my') {
        speedFieldState.my_tailwind = !speedFieldState.my_tailwind;
    } else if (side === 'opp') {
        speedFieldState.opp_tailwind = !speedFieldState.opp_tailwind;
    }
    updateTailwindButtons();
    renderSpeedAxis();
    if (typeof refreshDamage === 'function') refreshDamage();
}

function toggleFieldEffect(key) {
    speedFieldState[key] = !speedFieldState[key];
    const btn = document.getElementById('btn-' + key);
    if (btn) btn.classList.toggle('active', speedFieldState[key]);
    if (typeof refreshDamage === 'function') refreshDamage();
}

function updateAllFieldButtons() {
    const keys = [
        'my_friendGuard','my_lightScreen','my_reflect','my_auroraVeil',
        'opp_friendGuard','opp_lightScreen','opp_reflect','opp_auroraVeil'
    ];
    keys.forEach(key => {
        const btn = document.getElementById('btn-' + key);
        if (btn) btn.classList.toggle('active', speedFieldState[key]);
    });
    updateWeatherButton();
    updateTerrainButton();
    updateTailwindButtons();
}

function setWeather(weather) {
    speedFieldState.weather = weather;
    updateWeatherButton();
    closeAllDropdowns();
    if (typeof refreshDamage === 'function') refreshDamage();
}

function setTerrain(terrain) {
    speedFieldState.terrain = terrain;
    updateTerrainButton();
    closeAllDropdowns();
    if (typeof refreshDamage === 'function') refreshDamage();
}

function updateWeatherButton() {
    const btn = document.getElementById('btn-weather');
    if (!btn) return;
    const w = speedFieldState.weather;
    const labels = { Sun:'晴天', Rain:'雨天', Sand:'沙暴', Hail:'雪天' };
    btn.textContent = w ? labels[w] : '天气';
    btn.classList.toggle('active', !!w);
    document.querySelectorAll('#weather-dropdown .speed-dropdown-item').forEach(el => {
        el.classList.toggle('selected', el.dataset.value === (w || ''));
    });
}

function updateTerrainButton() {
    const btn = document.getElementById('btn-terrain');
    if (!btn) return;
    const t = speedFieldState.terrain;
    const labels = { Electric:'电气', Grassy:'草场', Misty:'薄雾', Psychic:'超场' };
    btn.textContent = t ? labels[t] : '场地';
    btn.classList.toggle('active', !!t);
    document.querySelectorAll('#terrain-dropdown .speed-dropdown-item').forEach(el => {
        el.classList.toggle('selected', el.dataset.value === (t || ''));
    });
}


// ==================== 能力等级弹窗 ====================

function openBoostEditor(side, index) {
    const key = side === 'my-team' ? 'my' : 'opp';
    const pokemon = (currentTeams[side] || [])[index];
    if (!pokemon) return;
    const pokemonIndex = pokemon.index;
    const name = pokemon.name_zh || pokemon.name || '';
    if (!boostState[key][pokemonIndex]) {
        boostState[key][pokemonIndex] = { atk: 0, def: 0, spa: 0, spd: 0, spe: 0 };
    }
    const boosts = boostState[key][pokemonIndex];

    const overlay = document.createElement('div');
    overlay.id = 'boost-editor-overlay';
    overlay.className = 'boost-editor-overlay';

    const stats = [
        { key: 'atk', label: '攻击' },
        { key: 'def', label: '防御' },
        { key: 'spa', label: '特攻' },
        { key: 'spd', label: '特防' },
        { key: 'spe', label: '速度' }
    ];

    const levelNumsHtml = [1,2,3,4,5,6].map(n =>
        `<span class="boost-level-num">+${n}</span>`
    ).join('');

    const rowsHtml = stats.map(s => {
        let arrowsHtml = '';
        const val = boosts[s.key];
        for (let lv = 1; lv <= 6; lv++) {
            const upActive = val > 0 && lv <= val ? ' active' : '';
            const downActive = val < 0 && lv <= -val ? ' active' : '';
            arrowsHtml += `
                <div class="boost-arrow-pair">
                    <div class="boost-arrow boost-up${upActive}" data-stat="${s.key}" data-level="${lv}" data-sign="1">▲</div>
                    <div class="boost-arrow boost-down${downActive}" data-stat="${s.key}" data-level="${lv}" data-sign="-1">▼</div>
                </div>`;
        }
        return `
            <div class="boost-row">
                <span class="boost-stat-label">${s.label}</span>
                <div class="boost-arrows">${arrowsHtml}</div>
            </div>`;
    }).join('');

    overlay.innerHTML = `
        <div class="boost-editor-box">
            <div class="boost-editor-header">
                <span>${name}</span>
                <button class="boost-editor-close-btn" id="boost-close-btn">×</button>
            </div>
            <div class="boost-level-labels">
                <span class="boost-stat-label"></span>
                <div class="boost-arrows">${levelNumsHtml}</div>
            </div>
            <div class="boost-rows">${rowsHtml}</div>
            <div class="boost-editor-footer">
                <button class="boost-reset-btn" id="boost-reset-btn">重置</button>
                <button class="boost-confirm-btn" id="boost-confirm-btn">确定</button>
            </div>
        </div>`;

    overlay._boostSide = side;
    overlay._boostPokemonIndex = pokemonIndex;

    document.body.appendChild(overlay);
    requestAnimationFrame(() => overlay.classList.add('open'));

    // 关闭按钮
    overlay.querySelector('#boost-close-btn').addEventListener('click', () => closeBoostEditor());
    // 重置按钮
    overlay.querySelector('#boost-reset-btn').addEventListener('click', () => resetBoosts());
    // 确认按钮
    overlay.querySelector('#boost-confirm-btn').addEventListener('click', () => confirmBoosts());
    // 点击遮罩层关闭
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) closeBoostEditor();
    });

    // 箭头点击事件委托
    overlay.addEventListener('click', (e) => {
        const arrow = e.target.closest('.boost-arrow');
        if (!arrow) return;
        onBoostArrowClick(arrow.dataset.stat, parseInt(arrow.dataset.level), parseInt(arrow.dataset.sign), side, pokemonIndex);
    });
}

function onBoostArrowClick(stat, level, sign, side, pokemonIndex) {
    const key = (side === 'my-team' || side === 'my') ? 'my' : 'opp';
    if (!boostState[key][pokemonIndex]) {
        boostState[key][pokemonIndex] = { atk: 0, def: 0, spa: 0, spd: 0, spe: 0 };
    }
    const current = boostState[key][pokemonIndex][stat];
    boostState[key][pokemonIndex][stat] = (current === level * sign) ? 0 : level * sign;
    const newVal = boostState[key][pokemonIndex][stat];

    const overlay = document.getElementById('boost-editor-overlay');
    if (!overlay) return;
    overlay.querySelectorAll(`.boost-arrow[data-stat="${stat}"]`).forEach(el => {
        const lv = parseInt(el.dataset.level);
        const sg = parseInt(el.dataset.sign);
        const isActive = (newVal > 0 && sg === 1 && lv <= newVal) ||
                         (newVal < 0 && sg === -1 && lv <= -newVal);
        el.classList.toggle('active', isActive);
    });
}

function resetBoosts() {
    const overlay = document.getElementById('boost-editor-overlay');
    if (!overlay) return;
    const key = overlay._boostSide === 'my-team' ? 'my' : 'opp';
    boostState[key][overlay._boostPokemonIndex] = { atk: 0, def: 0, spa: 0, spd: 0, spe: 0 };
    overlay.querySelectorAll('.boost-arrow').forEach(el => el.classList.remove('active'));
}

function confirmBoosts() {
    closeBoostEditor();
    renderSpeedAxis();
    updateCardBoostIndicators();
    if (typeof refreshDamage === 'function') refreshDamage();
}

function updateCardBoostIndicators() {
    ['my-team', 'opp-team'].forEach(side => {
        const cards = document.querySelectorAll(`.team-col.${side} .pokemon-card`);
        cards.forEach((card, i) => {
            const pokemon = (currentTeams[side] || [])[i];
            if (!pokemon) return;
            const statsDiv = card.querySelector('.card-stats');
            if (!statsDiv) return;
            const boosts = boostState[side === 'my-team' ? 'my' : 'opp']?.[pokemon.index];
            statsDiv.innerHTML = renderStats(pokemon.base_stats, pokemon.stats, pokemon.nature, boosts);
        });
    });
}

function closeBoostEditor() {
    const overlay = document.getElementById('boost-editor-overlay');
    if (overlay) {
        overlay.classList.remove('open');
        setTimeout(() => overlay.remove(), 200);
    }
}


function renderSpeedAxisTicks(maxSpeed) {
    const axisMain = document.getElementById('speed-axis-main');
    if (!axisMain) return;

    const staticTicks = axisMain.querySelectorAll('.speed-tick:not(.speed-my-tick)');
    staticTicks.forEach((tick) => tick.remove());

    const tickValues = [];
    for (let value = MIN_SPEED; value <= maxSpeed; value += AXIS_MAJOR_STEP) {
        tickValues.push(value);
    }
    if (!tickValues.includes(maxSpeed)) {
        tickValues.push(maxSpeed);
    }

    tickValues.forEach((value) => {
        const tickEl = document.createElement('div');
        tickEl.className = 'speed-tick';
        tickEl.style.left = `${speedToPercent(value, maxSpeed)}%`;
        tickEl.innerHTML = `<span>${value}</span>`;
        axisMain.appendChild(tickEl);
    });
}


function clamp(value, minValue, maxValue) {
    return Math.max(minValue, Math.min(value, maxValue));
}


function startOppSpeedDrag(event, globalIndex, rowEl, pctMin, pctMax) {
    event.preventDefault();
    event.stopPropagation();

    const rowRect = rowEl.getBoundingClientRect();
    const rangeWidth = Math.max(pctMax - pctMin, 0.0001);
    const currentRatio = clamp(oppSpeedMarkerRatio[globalIndex] ?? 0.5, 0, 1);
    const currentPct = pctMin + rangeWidth * currentRatio;
    const pointerPct = ((event.clientX - rowRect.left) / rowRect.width) * 100;
    const pointerOffsetPct = pointerPct - currentPct;

    oppSpeedDragState = {
        globalIndex,
        rowEl,
        pctMin,
        pctMax,
        pointerOffsetPct
    };

    rowEl.classList.add('dragging');
    document.addEventListener('mousemove', onOppSpeedDragMove);
    document.addEventListener('mouseup', stopOppSpeedDrag);
}


function onOppSpeedDragMove(event) {
    if (!oppSpeedDragState) return;

    const { globalIndex, rowEl, pctMin, pctMax, pointerOffsetPct } = oppSpeedDragState;
    const rowRect = rowEl.getBoundingClientRect();
    if (!rowRect.width) return;

    const pointerPct = ((event.clientX - rowRect.left) / rowRect.width) * 100;
    const nextPct = clamp(pointerPct - pointerOffsetPct, pctMin, pctMax);
    const rangeWidth = Math.max(pctMax - pctMin, 0.0001);
    const nextRatio = clamp((nextPct - pctMin) / rangeWidth, 0, 1);

    oppSpeedMarkerRatio[globalIndex] = nextRatio;

    const spriteEl = rowEl.querySelector('.speed-opp-sprite');
    if (spriteEl) {
        spriteEl.style.left = `${nextPct}%`;
    }
}


function stopOppSpeedDrag() {
    if (oppSpeedDragState && oppSpeedDragState.rowEl) {
        oppSpeedDragState.rowEl.classList.remove('dragging');
    }

    oppSpeedDragState = null;
    document.removeEventListener('mousemove', onOppSpeedDragMove);
    document.removeEventListener('mouseup', stopOppSpeedDrag);
}


function resetOppSpeedMarkerRatio() {
    oppSpeedMarkerRatio = {};
    stopOppSpeedDrag();
}


function renderTypeIcon(typeName, className = 'type-icon') {
    const key = typeName.charAt(0).toUpperCase() + typeName.slice(1);
    const typeId = TYPE_ID_MAP[key] || 1;
    return `<div class="${className}" title="${key}" style="background-image: url('/sprites/sprites/types/generation-ix/scarlet-violet/small/${typeId}.png')"></div>`;
}

function renderAbility(ability) {
    if (!ability || !Array.isArray(ability) || !ability.length) return '';
    return ability.map(a => {
        const name = a.name_zh || a.name || '';
        const pctStr = a.pct ? ` (${Math.round(a.pct * 100)}%)` : '';
        const desc = a.description_zh || a.description || '';
        const title = `${name}${pctStr}\n${desc}`;
        return `<span class="card-ability" title="${title.replace(/"/g, '&quot;')}">${name}</span>`;
    }).join(', ');
}

function renderItem(heldItem) {
    if (!heldItem || !Array.isArray(heldItem) || !heldItem.length) return '<span class="card-item" title="">无道具</span>';
    return heldItem.map(i => {
        const name = i.name_zh || i.name || '';
        const pctStr = i.pct ? ` (${Math.round(i.pct * 100)}%)` : '';
        const desc = i.description_zh || i.description || '';
        const title = `${name}${pctStr}\n${desc}`;
        return `<span class="card-item" title="${title.replace(/"/g, '&quot;')}">${name}</span>`;
    }).join(', ');
}

function renderEvoButtons(evoforms, currentEvoIndex, side, index) {
    if (!evoforms || !evoforms.length) return '';
    return evoforms.map((evo, evoIdx) => {
        const buttonName = evo.form_name || 'mega';
        const isActive = currentEvoIndex === evoIdx ? 'active' : '';
        return `<button class="evo-button ${isActive}" onclick="switchEvoform('${side}', ${index}, ${evoIdx})" title="切换至 ${buttonName}">${buttonName}</button>`;
    }).join('');
}

function renderMoves(moves, side, index) {
    return moves.map((m, moveIdx) => {
        const powerAccuracy = m.power !== null ? `${m.power}/${m.accuracy ?? '-'}` : '-/-';
        const prio = Number(m.priority || 0);
        const priorityPrefix = prio !== 0 ? (prio > 0 ? `+${prio}` : `${prio}`) : '';
        const desc = m.short_effect_zh || m.short_effect || '';
        const pctStr = m.pct ? `使用率: ${Math.round(m.pct * 100)}%` : '';
        const moveTitle = [desc, pctStr].filter(Boolean).join('\n');
        const moveName = m.name_zh || m.name || '';
        const clickableClass = (side === 'my-team' || side === 'opp-team') ? ' clickable' : '';
        const clickAttr = (side === 'my-team' || side === 'opp-team')
            ? ` onclick="showMoveDamageRange('${side}', ${index}, ${moveIdx})"`
            : '';
        const nameDisplay = priorityPrefix ? `${priorityPrefix}${moveName}` : moveName;
        return `<div class="move-chip type-${m.type.toLowerCase()}${clickableClass}" title="${moveTitle.replace(/"/g, '&quot;')}"${clickAttr}>${nameDisplay}<span class="move-stats">${powerAccuracy}</span></div>`;
    }).join('');
}

function renderStats(baseStats, stats, nature, boosts) {
    const labels = [
        { key: 'hp', label: 'HP', boostKey: null },
        { key: 'attack', label: 'A', boostKey: 'atk' },
        { key: 'defense', label: 'D', boostKey: 'def' },
        { key: 'sp_atk', label: 'SA', boostKey: 'spa' },
        { key: 'sp_def', label: 'SD', boostKey: 'spd' },
        { key: 'speed', label: 'S', boostKey: 'spe' }
    ];
    let upStat = '', downStat = '';
    if (nature) {
        const [up, down] = nature.split('/');
        upStat = up ? up.split('↑')[0] : '';
        downStat = down ? down.split('↓')[0] : '';
    }
    return labels.map(({ key, label, boostKey }) => {
        const base = baseStats[key];
        const current = stats[key];
        let labelClass = '';
        if (upStat && upStat.toLowerCase() === key.toLowerCase()) labelClass = 'nature-up';
        else if (downStat && downStat.toLowerCase() === key.toLowerCase()) labelClass = 'nature-down';
        const boost = boosts && boostKey ? (boosts[boostKey] || 0) : 0;
        const boostHtml = boost !== 0
            ? `<span class="stat-boost ${boost > 0 ? 'stat-boost-up' : 'stat-boost-down'}">${boost > 0 ? '+' : ''}${boost}</span>`
            : '';
        return `<div class="stat-row"><span class="stat-label ${labelClass}">${label}${boostHtml}</span><span class="stat-value ${labelClass}">${current}</span></div>`;
    }).join('');
}

function renderEvEditor(evs, side, index) {
    const labels = [
        { key: 'hp', label: 'HP' },
        { key: 'attack', label: 'A' },
        { key: 'defense', label: 'D' },
        { key: 'sp_atk', label: 'SA' },
        { key: 'sp_def', label: 'SD' },
        { key: 'speed', label: 'S' }
    ];
    return labels.map(({ key, label }) => {
        const ev = evs?.[key] ?? 0;
        return `
            <div class="ev-row">
                <span class="stat-label">${label}</span>
                <input type="range" class="ev-slider" min="0" max="32" value="${ev}" oninput="onEvSliderInput(this, '${side}', ${index}, '${key}')">
                <input type="number" class="ev-number" min="0" max="32" value="${ev}" onchange="onEvNumberChange(this, '${side}', ${index}, '${key}')">
            </div>
        `;
    }).join('');
}

function renderEffectiveness(effectiveness) {
    const groups = {};
    for (const [type, mult] of Object.entries(effectiveness)) {
        (groups[mult] = groups[mult] || []).push(type);
    }
    const labels = { 4: '×4', 2: '×2', 0.25: '÷4', 0.5: '÷2', 0: '×0' };
    const weakRows = [];
    for (const mult of [4, 2]) {
        if (groups[mult]) {
            weakRows.push(`<div class="effectiveness-row"><span class="effectiveness-label">${labels[mult]}:</span>${groups[mult].map(t => renderTypeIcon(t, 'type-icon-small')).join('')}</div>`);
        }
    }
    const resistRows = [];
    for (const mult of [0.25, 0.5, 0]) {
        if (groups[mult]) {
            resistRows.push(`<div class="effectiveness-row"><span class="effectiveness-label">${labels[mult]}:</span>${groups[mult].map(t => renderTypeIcon(t, 'type-icon-small')).join('')}</div>`);
        }
    }
    const hasWeak = weakRows.length > 0;
    const hasResist = resistRows.length > 0;
    if (!hasWeak && !hasResist) return '';
    const parts = [];
    if (hasWeak) {
        parts.push('<div class="weakness-label">弱点</div>');
        parts.push(`<div class="effectiveness-rows">${weakRows.join('')}</div>`);
    }
    if (hasResist) {
        parts.push('<div class="resist-label">抵抗</div>');
        parts.push(`<div class="effectiveness-rows">${resistRows.join('')}</div>`);
    }
    return `<div class="effectiveness-grid">${parts.join('')}</div>`;
}

function renderCard(pokemon, side, index) {
    const inner = document.createElement('div');
    inner.className = 'card-inner';
    const spritePath = pokemon.sprite.replace(/^sprites\//, '');

    const typeIcons = pokemon.types.map(t => renderTypeIcon(t)).join('');
    const evoButtonsHtml = renderEvoButtons(pokemon.evoforms, pokemon._currentEvoIndex, side, index);

    const editBtnHtml = (side === 'opp-team')
        ? `<button class="card-name-edit" onclick="openPokemonSwitcher('${side}', ${index})" title="切换宝可梦">✏️</button>`
        : '';

    inner.innerHTML = `
        <div class="card-bg-sprite" style="background-image: url('/sprites/${spritePath}')"></div>
        <div class="card-info">
            <div class="card-info-left">
                <div class="card-meta">
                    ${renderItem(pokemon.held_item)}
                </div>
                <div class="card-meta">
                    ${renderAbility(pokemon.ability)}
                </div>
                <div class="card-moves-section">
                    <div class="card-moves">${renderMoves(pokemon.moves, side, index)}</div>
                </div>
            </div>
            <div class="card-info-right">
                <div class="card-info-right-top">
                    <div class="card-header-section">
                        <div class="card-header">
                            <div class="card-types">${typeIcons}</div>
                            <span class="card-name">${pokemon.name_zh || pokemon.name || ''}</span>${editBtnHtml}
                            ${evoButtonsHtml ? `<div class="evo-buttons">${evoButtonsHtml}</div>` : ''}
                        </div>
                    </div>
                </div>
                <div class="card-info-right-bottom">
                    <div class="card-effectiveness-section">
                        <div class="card-effectiveness">
                            ${renderEffectiveness(pokemon.type_effectiveness)}
                        </div>
                    </div>
                    <div class="card-stats-section">
                        <div class="card-stats">${renderStats(pokemon.base_stats, pokemon.stats, pokemon.nature, boostState[side === 'my-team' ? 'my' : 'opp']?.[pokemon.index])}</div>
                        <div class="card-evs" style="display:none">
                            <div class="ev-header">
                                <span class="stat-label">EVs</span>
                                <span class="ev-header-back">← 返回</span>
                            </div>
                            <div class="ev-content">
                                <div class="ev-sliders-col">${renderEvEditor(pokemon.evs, side, index)}</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>`;

    // EV editor toggle
    const statsDiv = inner.querySelector('.card-stats');
    const evsDiv = inner.querySelector('.card-evs');
    if (statsDiv && evsDiv) {
        statsDiv.addEventListener('click', () => {
            closeAllOppEvEditors();
            evsDiv.style.display = '';
            statsDiv.style.display = 'none';
            if (side === 'opp-team' && Array.isArray(pokemon.evList) && pokemon.evList.length > 0) {
                showEvListPanel(side, index);
            }
        });
        const backBtn = evsDiv.querySelector('.ev-header-back');
        if (backBtn) {
            backBtn.addEventListener('click', () => {
                evsDiv.style.display = 'none';
                statsDiv.style.display = '';
                closeEvListPanel();
            });
        }
    }

    // 能力等级弹窗：点击 .card-info 空白区域触发
    const cardInfo = inner.querySelector('.card-info');
    if (cardInfo) {
        cardInfo.addEventListener('click', (e) => {
            if (e.target.closest('.move-chip, .card-stats, .card-name-edit, .evo-button, .ev-slider, .ev-number, .ev-header-back, .card-item, .card-ability')) return;
            openBoostEditor(side, index);
        });
    }

    return inner;
}

function renderTeam(team, side) {
    const cards = document.querySelectorAll(`.team-col.${side} .pokemon-card`);
    cards.forEach((card, i) => {
        card.innerHTML = '';
        if (team[i]) card.appendChild(renderCard(team[i], side, i));
    });
    renderSpeedAxis();
}


// EV inline event handlers
function onEvSliderInput(el, side, index, key) {
    console.log("onEvSliderInput",el)
    const v = Math.min(32, Math.max(0, parseInt(el.value) || 0));
    el.value = v;
    const row = el.closest('.ev-row');
    const number = row?.querySelector('.ev-number');
    if (number) number.value = v;
    updatePokemonEv(side, index, key, v);
}

function onEvNumberChange(el, side, index, key) {
    console.log("onEvNumberChange",el)
    const v = Math.min(32, Math.max(0, parseInt(el.value) || 0));
    el.value = v;
    const row = el.closest('.ev-row');
    const slider = row?.querySelector('.ev-slider');
    if (slider) slider.value = v;
    
    updatePokemonEv(side, index, key, v);
}

function updatePokemonEv(side, index, key, v) {
    try {
        const pokemon = currentTeams[side]?.[index];
        if (!pokemon) return;
        if (!pokemon.evs) pokemon.evs = {};
        pokemon.evs[key] = v;

        // const typeOverlay = document.getElementById('damage-info');
        // if (typeOverlay && typeOverlay.classList.contains('open')) {
            if (typeof showDamageInfo === 'function') showDamageInfo();
            if (typeof showDamageInfoDetail === 'function') showDamageInfoDetail();
        // }
        // const moveOverlay = document.getElementById('move-damage-overlay');
        // if (moveOverlay && moveOverlay.classList.contains('open') && activeDamageQuery) {
        //     if (typeof showMoveDamageRange === 'function')
        //         showMoveDamageRange(activeDamageQuery.side, activeDamageQuery.pokemonIndex, activeDamageQuery.moveIndex);
        // }
    } catch (e) {
        console.error('updatePokemonEv error:', e);
    }
}

function applyEvListEntry(side, index, el) {
    const pokemon = currentTeams[side]?.[index];
    if (!pokemon) return;
    const entry = pokemon.evList?.[parseInt(el.dataset.idx)];
    if (!entry) return;
    const statMap = { hp: 'hp', atk: 'attack', def: 'defense', spA: 'sp_atk', spD: 'sp_def', spe: 'speed' };
    if (!pokemon.evs) pokemon.evs = {};
    for (const [k, v] of Object.entries(entry)) {
        if (k === 'pct') continue;
        const key = statMap[k];
        if (key !== undefined) pokemon.evs[key] = v;
    }
    // 通过 side/index 精确定位卡片中的滑杆和数字输入
    const card = document.querySelector(`.team-col.${side} .pokemon-card:nth-child(${index + 1})`);
    if (card) {
        card.querySelectorAll('.ev-slider').forEach((sl, i) => {
            sl.value = pokemon.evs[['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed'][i]] ?? 0;
        });
        card.querySelectorAll('.ev-number').forEach((num, i) => {
            num.value = pokemon.evs[['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed'][i]] ?? 0;
        });
    }
    // 高亮当前选中的条目
    const panel = document.getElementById('evlist-panel');
    if (panel) panel.querySelectorAll('.evlist-entry').forEach(e => e.classList.remove('active'));
    el.classList.add('active');
    if (typeof showDamageInfo === 'function') showDamageInfo();
    if (typeof showDamageInfoDetail === 'function') showDamageInfoDetail();
}

function showEvListPanel(side, index) {
    closeEvListPanel();
    const pokemon = currentTeams[side]?.[index];
    if (!pokemon || !Array.isArray(pokemon.evList) || pokemon.evList.length === 0) return;
    const panel = document.createElement('div');
    panel.className = 'evlist-panel';
    panel.id = 'evlist-panel';
    panel.innerHTML = `
        <div class="evlist-header">
            <span>常用努力值</span>
            <button onclick="closeEvListPanel()">✕</button>
        </div>
        <div class="evlist-body">
            <div class="evlist-tr evlist-header-row">
                <span class="evlist-th">HP</span>
                <span class="evlist-th">A</span>
                <span class="evlist-th">D</span>
                <span class="evlist-th">SA</span>
                <span class="evlist-th">SD</span>
                <span class="evlist-th">S</span>
                <span class="evlist-th">%</span>
            </div>
            ${pokemon.evList.map((entry, i) => `
                <div class="evlist-tr evlist-entry ${i === 0 ? 'active' : ''}" data-idx="${i}" onclick="applyEvListEntry('${side}', ${index}, this)">
                    <span class="evlist-td">${entry.hp}</span>
                    <span class="evlist-td">${entry.atk}</span>
                    <span class="evlist-td">${entry.def}</span>
                    <span class="evlist-td">${entry.spA}</span>
                    <span class="evlist-td">${entry.spD}</span>
                    <span class="evlist-td">${entry.spe}</span>
                    <span class="evlist-td evlist-td-pct">${entry.pct}%</span>
                </div>
            `).join('')}
        </div>
    `;
    document.body.appendChild(panel);
}

function closeEvListPanel() {
    const panel = document.getElementById('evlist-panel');
    if (panel) panel.remove();
}

function closeAllOppEvEditors() {
    document.querySelectorAll('.team-col.opp-team .pokemon-card').forEach(card => {
        const evs = card.querySelector('.card-evs');
        const stats = card.querySelector('.card-stats');
        if (evs) evs.style.display = 'none';
        if (stats) stats.style.display = '';
    });
}

function closeMoveDamageOverlay() {
    const overlay = document.getElementById('move-damage-overlay');
    if (!overlay) return;
    overlay.classList.remove('open');
}


function updateBattleModeToggleLabel() {
    const toggle = document.getElementById('battle-mode-toggle');
    if (!toggle) return;
    toggle.textContent = battleMode === 'double' ? '双打' : '单打';
}


function toggleBattleMode() {
    battleMode = battleMode === 'double' ? 'single' : 'double';
    updateBattleModeToggleLabel();
}


function onMoveDamageOverlayDragMove(event) {
    if (!moveDamageDragState) return;
    const overlay = moveDamageDragState.overlay;
    const nextLeft = event.clientX - moveDamageDragState.offsetX;
    const nextTop = event.clientY - moveDamageDragState.offsetY;
    overlay.style.left = `${Math.max(0, nextLeft)}px`;
    overlay.style.top = `${Math.max(0, nextTop)}px`;
    overlay.style.right = 'auto';
}


function stopMoveDamageOverlayDrag() {
    moveDamageDragState = null;
    document.removeEventListener('mousemove', onMoveDamageOverlayDragMove);
    document.removeEventListener('mouseup', stopMoveDamageOverlayDrag);
}


function startMoveDamageOverlayDrag(event) {
    const overlay = document.getElementById('move-damage-overlay');
    if (!overlay) return;
    if (event.target.closest('button')) return;

    const rect = overlay.getBoundingClientRect();
    moveDamageDragState = {
        overlay: overlay,
        offsetX: event.clientX - rect.left,
        offsetY: event.clientY - rect.top
    };
    document.addEventListener('mousemove', onMoveDamageOverlayDragMove);
    document.addEventListener('mouseup', stopMoveDamageOverlayDrag);
}


function initMoveDamageOverlayDrag() {
    const header = document.querySelector('#move-damage-overlay .move-damage-header');
    if (!header || header.dataset.dragBound === '1') return;
    header.dataset.dragBound = '1';
    header.addEventListener('mousedown', startMoveDamageOverlayDrag);
}


function renderMoveDamageRows(rows) {
    const content = document.getElementById('move-damage-content');
    if (!content) return;
    if (!rows || !rows.length) {
        content.textContent = '没有可展示的目标。';
        return;
    }

    content.innerHTML = rows.map((row) => {
        const name = row.opp_name_zh || row.opp_name || '-';
        const types = row.opp_types || [];
        const range = row.range || {};
        const dmgText = `${range.damage_min} - ${range.damage_max}`;
        const hpText = `${range.hp_pct_min}% - ${range.hp_pct_max}%`;
        const typeMult = Number(range.type_multiplier || 1).toFixed(2);
        const hpRangeText = `${row.opp_hp_min || 0} - ${row.opp_hp_max || 0}`;
        const typeIcons = types.map((typeName) => {
            const typeId = TYPE_ID_MAP[typeName] || 1;
            return `<div class="type-icon-small" style="background-image: url('/sprites/sprites/types/generation-ix/scarlet-violet/small/${typeId}.png')" title="${typeName}"></div>`;
        }).join('');
        return `
            <div class="move-damage-row">
                <div class="move-damage-name-row">
                    <div class="move-damage-row-name">${name}</div>
                    <div class="move-damage-type-icons">${typeIcons}</div>
                </div>
                <div class="move-damage-row-range">极限HP: ${hpRangeText}</div>
                <div class="move-damage-row-range">伤害: ${dmgText}</div>
                <div class="move-damage-row-range">生命值: ${hpText} (x${typeMult})</div>
            </div>
        `;
    }).join('');
}


function showMoveDamageRange(side, pokemonIndex, moveIndex) {
    activeDamageQuery = { side: side, pokemonIndex: pokemonIndex, moveIndex: moveIndex };
    const myTeam = currentTeams['my-team'] || [];
    const oppTeam = currentTeams['opp-team'] || [];
    const isMySide = side === 'my-team';
    const attackerTeam = isMySide ? myTeam : oppTeam;
    const targetTeam = isMySide ? oppTeam : myTeam;
    const attacker = attackerTeam[pokemonIndex];
    const overlay = document.getElementById('move-damage-overlay');
    const title = document.getElementById('move-damage-title');
    const content = document.getElementById('move-damage-content');

    if (!overlay || !title || !content) return;
    if (!attacker || !attacker.moves || !attacker.moves[moveIndex]) return;
    if (!targetTeam.length) {
        title.textContent = '技能伤害范围';
        content.textContent = isMySide ? '请先生成对方队伍。' : '请先生成我方队伍。';
        overlay.classList.add('open');
        return;
    }

    const move = attacker.moves[moveIndex];
    title.textContent = `${attacker.name_zh || attacker.name} - ${move.name_zh || move.name}`;
    content.textContent = '计算中...';
    overlay.classList.add('open');

    if (!move || move.category === 'status' || move.power == null) {
        content.textContent = '该技能非伤害技能';
        return;
    }

    try {
        const rows = [];
        for (const defender of targetTeam) {
            if (!defender) continue;
            const res = calcDamage(attacker, defender, move, { attackerSide: isMySide ? 'my' : 'opp', defenderSide: isMySide ? 'opp' : 'my' });
            if (!res) continue;
            const [dmgMin, dmgMax] = res.range();
            const effectiveness = res.effectiveness || 1;
            const hp = getPokemonHP(defender);
            if (hp <= 0) continue;
            rows.push({
                opp_name: defender.name || '',
                opp_name_zh: defender.name_zh || '',
                opp_types: defender.types || [],
                opp_hp_min: hp,
                opp_hp_max: hp,
                range: {
                    damage_min: dmgMin,
                    damage_max: dmgMax,
                    hp_pct_min: +(dmgMin / hp * 100).toFixed(2),
                    hp_pct_max: +(dmgMax / hp * 100).toFixed(2),
                    type_multiplier: effectiveness,
                },
            });
        }

        if (rows.length === 0) {
            content.textContent = '没有可展示的目标。';
            return;
        }

        rows.sort((a, b) => {
            if (b.range.hp_pct_max !== a.range.hp_pct_max) return b.range.hp_pct_max - a.range.hp_pct_max;
            return b.range.hp_pct_min - a.range.hp_pct_min;
        });

        if (Number(move.priority || 0) !== 0) {
            const p = Number(move.priority);
            title.textContent += `（先制度 ${p >= 0 ? '+' : ''}${p}）`;
        }
        const isDouble = battleMode === 'double' || battleMode === 'doubles' || battleMode === 2;
        if (isDouble && isSpreadMove(move)) {
            title.textContent += '（双打范围修正）';
        }
        if (isGuaranteedCriticalMove(move)) {
            title.textContent += '（必定要害修正）';
        }
        if (isMultiHitMove(move)) {
            title.textContent += '（多段技能，当前为单段伤害）';
        }

        renderMoveDamageRows(rows);
    } catch (err) {
        content.textContent = `计算错误：${err.message}`;
    }
}

window.addEventListener('load', () => {
    loadTeamMenus();
    initMoveDamageOverlayDrag();
    updateBattleModeToggleLabel();
});

// Team management
async function loadTeamMenus() {
    const res = await fetch('/api/teams');
    const data = await res.json();
    const teams = data.teams || [];

    // Load submenu
    const loadSub = document.getElementById('load-team-submenu');
    loadSub.innerHTML = teams.length
        ? teams.map(t => `<div class="dropdown-item" onclick="event.stopPropagation(); loadTeamSlot('${t.id}')">${t.slot_name}</div>`).join('')
        : '<div class="dropdown-item" style="color:#888">暂无队伍</div>';

    // Save submenu
    const saveSub = document.getElementById('save-team-submenu');
    const existingItems = teams.map(t =>
        `<div class="dropdown-item" onclick="event.stopPropagation(); saveTeamToSlot('${t.id}')">${t.slot_name}</div>`
    ).join('');
    saveSub.innerHTML = existingItems +
        `<div class="dropdown-item" onclick="event.stopPropagation(); saveTeamAsNew()">+ 新建</div>`;

    // Delete submenu
    const delSub = document.getElementById('delete-team-submenu');
    delSub.innerHTML = teams.length
        ? teams.map(t => `<div class="dropdown-item" onclick="event.stopPropagation(); deleteTeamSlot('${t.id}','${t.slot_name}')">${t.slot_name}</div>`).join('')
        : '<div class="dropdown-item" style="color:#888">暂无队伍</div>';
}

async function loadTeamSlot(slotId) {
    closeAllMenus();
    const res = await fetch(`/api/teams/load/${slotId}`, { method: 'POST' });
    const data = await res.json();
    if (data.success) {
        currentTeams['my-team'] = data.team.roster;
        renderTeam(currentTeams['my-team'], 'my-team');
        logMsg(`队伍已读取：${data.team.slot_name || slotId}`);
    }
}

async function saveTeamToSlot(slotId) {
    closeAllMenus();
    const res = await fetch('/api/teams/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slot_id: slotId })
    });
    const data = await res.json();
    if (data.success) {
        logMsg(`队伍已写入：${data.slot_name}`);
        loadTeamMenus();
    }
}

async function saveTeamAsNew() {
    closeAllMenus();
    const name = window.prompt('请输入队伍名称：', '');
    if (name === null) return;
    const res = await fetch('/api/teams/save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ slot_name: name || '新队伍' })
    });
    const data = await res.json();
    if (data.success) {
        logMsg(`新队伍已保存：${data.slot_name}`);
        loadTeamMenus();
    }
}

async function deleteTeamSlot(slotId, slotName) {
    closeAllMenus();
    if (!confirm(`确定删除「${slotName}」吗？`)) return;
    const res = await fetch(`/api/teams/${slotId}`, { method: 'DELETE' });
    const data = await res.json();
    if (data.success) {
        logMsg(`已删除：${slotName}`);
        loadTeamMenus();
    }
}

async function identifyTeam() {
    closeAllMenus();
    logMsg('正在识别队伍。请等待。');
    const res = await fetch('/api/teams/generate', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
        openDraftEditor(data.draft);
        logMsg('识别完成，请编辑并确认。');
    } else {
        logMsg(`识别失败：${data.error}`);
    }
}

let currentDraft = null;

function openDraftEditor(draft) {
    currentDraft = JSON.parse(JSON.stringify(draft));
    const overlay = document.getElementById('draft-editor-overlay');
    const tabBar = document.getElementById('draft-tab-bar');
    const panels = document.getElementById('draft-tab-panels');

    tabBar.innerHTML = '';
    panels.innerHTML = '';

    for (let i = 0; i < 6; i++) {
        const detectCard = currentDraft.detect_cards[i] || {};
        const moveCard = currentDraft.move_cards[i] || {};
        const statCard = currentDraft.stat_cards[i] || {};

        const tabBtn = document.createElement('button');
        tabBtn.className = i === 0 ? 'active' : '';
        tabBtn.textContent = `${i + 1}`;
        tabBtn.onclick = () => switchDraftTab(i);
        tabBar.appendChild(tabBtn);

        const panel = document.createElement('div');
        panel.className = `draft-tab-panel ${i === 0 ? 'active' : ''}`;
        panel.id = `draft-panel-${i}`;

        const slot = document.createElement('div');
        slot.className = 'draft-pokemon-slot';

        const sprite = document.createElement('div');
        sprite.className = 'draft-pokemon-sprite';
        const spriteImg = document.createElement('img');
        spriteImg.id = `dc-sprite-${i}`;
        if (detectCard.sprite_key) {
            const spriteRelPath = detectCard.sprite_key.replace(/^sprites\//, '');
            spriteImg.src = `/sprites/${spriteRelPath}`;
        }
        sprite.appendChild(spriteImg);

        const fields = document.createElement('div');
        fields.className = 'draft-pokemon-fields';

        const slugGroup = createFieldGroup('Slug', `dc-slug-${i}`, detectCard.slug || '', false);
        slugGroup.querySelector('input').onblur = () => lookupSlug(i);
        fields.appendChild(slugGroup);

        const nameGroup = createFieldGroup('Pokemon', `dc-name-${i}`, detectCard.name || '', true);
        fields.appendChild(nameGroup);

        const nameGroup2 = document.createElement('div');
        nameGroup2.className = 'draft-field-group';
        const nameLabel2 = document.createElement('label');
        nameLabel2.textContent = '中文名';
        const nameContainer = document.createElement('div');
        nameContainer.style.display = 'flex';
        nameContainer.style.gap = '4px';
        const nameInputCN = document.createElement('input');
        nameInputCN.id = `dc-name-zh-${i}`;
        nameInputCN.type = 'text';
        nameInputCN.placeholder = '输入中文名...';
        nameInputCN.value = detectCard.name_zh || '';
        nameContainer.appendChild(nameInputCN);
        const queryBtn = document.createElement('button');
        queryBtn.textContent = '查询';
        queryBtn.style.padding = '6px 8px';
        queryBtn.style.background = '#0d7377';
        queryBtn.style.color = '#fff';
        queryBtn.style.border = 'none';
        queryBtn.style.borderRadius = '4px';
        queryBtn.style.cursor = 'pointer';
        queryBtn.style.fontSize = '12px';
        queryBtn.onclick = () => lookupNameZh(i);
        nameContainer.appendChild(queryBtn);
        nameGroup2.appendChild(nameLabel2);
        nameGroup2.appendChild(nameContainer);
        fields.appendChild(nameGroup2);

        const formGroup = document.createElement('div');
        formGroup.className = 'draft-field-group';
        const formLabel = document.createElement('label');
        formLabel.textContent = 'Form';
        const formSelect = document.createElement('select');
        formSelect.id = `dc-form-${i}`;
        formSelect.style.background = '#1a1a1a';
        formSelect.style.border = '1px solid #444';
        formSelect.style.color = '#ccc';
        formSelect.style.padding = '6px 8px';
        formSelect.style.borderRadius = '4px';
        formSelect.style.fontSize = '12px';
        formSelect.style.fontFamily = 'inherit';
        formSelect.style.cursor = 'pointer';
        formSelect.onchange = () => selectForm(i);
        const optionDefault = document.createElement('option');
        optionDefault.value = '';
        optionDefault.textContent = '-- 选择 --';
        formSelect.appendChild(optionDefault);
        formGroup.appendChild(formLabel);
        formGroup.appendChild(formSelect);
        fields.appendChild(formGroup);

        const nicknameGroup = createFieldGroup('昵称', `mc-nickname-${i}`, moveCard.nickname || '', false);
        fields.appendChild(nicknameGroup);

        const abilityGroup = createFieldGroup('特性', `mc-ability-${i}`, moveCard.ability || '', false);
        fields.appendChild(abilityGroup);

        const heldItemGroup = createFieldGroup('持有物', `mc-item-${i}`, moveCard.held_item || '', false);
        fields.appendChild(heldItemGroup);

        for (let j = 0; j < 4; j++) {
            const moveGroup = createFieldGroup(`招式${j + 1}`, `mc-move-${i}-${j}`, moveCard.moves?.[j] || '', false);
            fields.appendChild(moveGroup);
        }

        const statsRow = document.createElement('div');
        statsRow.className = 'draft-stats-row';
        const statNames = ['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed'];
        const statLabels = ['HP', 'Atk', 'Def', 'SpA', 'SpD', 'Spe'];
        for (let j = 0; j < 6; j++) {
            const statGroup = createFieldGroup(
                statLabels[j],
                `sc-stat-${i}-${statNames[j]}`,
                (statCard.stats?.[statNames[j]] || 0).toString(),
                false,
                'number'
            );
            statGroup.querySelector('input').onblur = () => recalcDraftEvs(i);
            statsRow.appendChild(statGroup);
        }
        fields.appendChild(statsRow);

        const evRow = document.createElement('div');
        evRow.className = 'draft-stats-row';
        for (let j = 0; j < 6; j++) {
            const evGroup = createFieldGroup(
                `${statLabels[j]}加点`,
                `sc-ev-${i}-${statNames[j]}`,
                statCard.evs?.[statNames[j]] === 0 ? '0' : (statCard.evs?.[statNames[j]] ?? '').toString(),
                false,
                'number'
            );
            evRow.appendChild(evGroup);
        }
        fields.appendChild(evRow);

        const natureGroup = createFieldGroup('性格', `sc-nature-${i}`, statCard.nature || '', false);
        natureGroup.style.gridColumn = '1 / -1';
        natureGroup.querySelector('input').onblur = () => recalcDraftEvs(i);
        fields.appendChild(natureGroup);

        if (statCard.warnings && statCard.warnings.length) {
            const warnDiv = document.createElement('div');
            warnDiv.className = 'draft-warnings';
            warnDiv.style.gridColumn = '1 / -1';
            warnDiv.style.color = '#ffb84d';
            warnDiv.style.fontSize = '12px';
            warnDiv.textContent = `⚠ ${statCard.warnings.join('；')}`;
            fields.appendChild(warnDiv);
        }

        slot.appendChild(sprite);
        slot.appendChild(fields);
        panel.appendChild(slot);
        panels.appendChild(panel);
    }

    overlay.classList.add('open');
}

async function recalcDraftEvs(slotIdx) {
    const slugInput = document.getElementById(`dc-slug-${slotIdx}`);
    const natureInput = document.getElementById(`sc-nature-${slotIdx}`);
    if (!slugInput || !natureInput) return;
    const slug = slugInput.value.trim();
    if (!slug) return;
    const nature = natureInput.value.trim();

    const statNames = ['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed'];
    const stats = {};
    for (const k of statNames) {
        stats[k] = parseInt(document.getElementById(`sc-stat-${slotIdx}-${k}`).value) || 0;
    }

    try {
        const res = await fetch(`/api/pokemon/calc-evs/${encodeURIComponent(slug)}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stats, nature })
        });
        const data = await res.json();
        if (!data.success) {
            logMsg(`加点重算失败: ${data.error}`);
            return;
        }
        for (const k of statNames) {
            const el = document.getElementById(`sc-ev-${slotIdx}-${k}`);
            if (el && data.evs[k] !== undefined && data.evs[k] !== null) {
                el.value = data.evs[k];
            }
        }
        if (!nature && data.nature) {
            natureInput.value = data.nature;
        }
    } catch (err) {
        logMsg(`加点重算错误: ${err.message}`);
    }
}

function createFieldGroup(label, inputId, value, readonly, type = 'text') {    const group = document.createElement('div');
    group.className = 'draft-field-group';

    const labelEl = document.createElement('label');
    labelEl.textContent = label;
    labelEl.htmlFor = inputId;

    const input = document.createElement('input');
    input.id = inputId;
    input.type = type;
    input.value = value;
    input.readOnly = readonly;

    group.appendChild(labelEl);
    group.appendChild(input);
    return group;
}

function switchDraftTab(idx) {
    const panels = document.querySelectorAll('.draft-tab-panel');
    const buttons = document.querySelectorAll('.draft-tab-bar button');

    panels.forEach((p, i) => {
        p.classList.toggle('active', i === idx);
    });

    buttons.forEach((btn, i) => {
        btn.classList.toggle('active', i === idx);
    });
}

async function lookupSlug(slotIdx) {
    const slugInput = document.getElementById(`dc-slug-${slotIdx}`);
    const slug = slugInput.value.trim();

    if (!slug) return;

    try {
        const res = await fetch(`/api/pokemon/detect-card/${slug}`);
        const data = await res.json();
        if (data.success) {
            const card = data.card;
            currentDraft.detect_cards[slotIdx] = card;

            document.getElementById(`dc-name-${slotIdx}`).value = card.name || '';

            const spriteImg = document.getElementById(`dc-sprite-${slotIdx}`);
            if (card.sprite_key) {
                const spriteRelPath = card.sprite_key.replace(/^sprites\//, '');
                spriteImg.src = `/sprites/${spriteRelPath}`;
            }

            logMsg(`已更新 Slot ${slotIdx + 1}: ${card.name}`);
        } else {
            logMsg(`Slug "${slug}" 不存在`);
        }
    } catch (err) {
        logMsg(`查询失败: ${err.message}`);
    }
}

async function lookupNameZh(slotIdx) {
    const nameInput = document.getElementById(`dc-name-zh-${slotIdx}`);
    const nameZh = nameInput.value.trim();

    if (!nameZh) return;

    try {
        const res = await fetch(`/api/pokemon/by-name-zh/${encodeURIComponent(nameZh)}`);
        const data = await res.json();
        if (data.success) {
            const variants = data.variants;
            const formSelect = document.getElementById(`dc-form-${slotIdx}`);
            formSelect.innerHTML = '<option value="">-- 选择 --</option>';
            variants.forEach(v => {
                const opt = document.createElement('option');
                opt.value = v.form || '';
                opt.textContent = v.form || '(默认)';
                formSelect.appendChild(opt);
            });
            // 自动选择第一个form（通常是默认的）
            if (variants.length > 0) {
                formSelect.value = variants[0].form || '';
                await selectForm(slotIdx);
            }
            logMsg(`找到 ${variants.length} 个形态`);
        } else {
            logMsg(`中文名 "${nameZh}" 不存在`);
        }
    } catch (err) {
        logMsg(`查询失败: ${err.message}`);
    }
}

async function selectForm(slotIdx) {
    const nameInput = document.getElementById(`dc-name-zh-${slotIdx}`);
    const formSelect = document.getElementById(`dc-form-${slotIdx}`);
    const nameZh = nameInput.value.trim();
    const form = formSelect.value;

    if (!nameZh) return;

    try {
        const formParam = form || '_none';
        const res = await fetch(`/api/pokemon/detect-card-by-name-form/${encodeURIComponent(nameZh)}/${encodeURIComponent(formParam)}`);
        const data = await res.json();
        if (data.success) {
            const card = data.card;
            currentDraft.detect_cards[slotIdx] = card;

            document.getElementById(`dc-slug-${slotIdx}`).value = card.slug || '';
            document.getElementById(`dc-name-${slotIdx}`).value = card.name || '';

            const spriteImg = document.getElementById(`dc-sprite-${slotIdx}`);
            if (card.sprite_key) {
                const spriteRelPath = card.sprite_key.replace(/^sprites\//, '');
                spriteImg.src = `/sprites/${spriteRelPath}`;
            }

            logMsg(`已更新 Slot ${slotIdx + 1}: ${card.name}/${form || '默认'}`);
        } else {
            logMsg(`查询失败: ${data.error}`);
        }
    } catch (err) {
        logMsg(`查询错误: ${err.message}`);
    }
}

function closeDraftEditor() {
    const overlay = document.getElementById('draft-editor-overlay');
    overlay.classList.remove('open');
    currentDraft = null;
}

async function buildTeamFromDraft() {
    if (!currentDraft) return;

    for (let i = 0; i < 6; i++) {
        const moveCard = currentDraft.move_cards[i];
        const statCard = currentDraft.stat_cards[i];

        moveCard.nickname = document.getElementById(`mc-nickname-${i}`).value;
        moveCard.ability = document.getElementById(`mc-ability-${i}`).value;
        moveCard.held_item = document.getElementById(`mc-item-${i}`).value;
        moveCard.moves = [
            document.getElementById(`mc-move-${i}-0`).value,
            document.getElementById(`mc-move-${i}-1`).value,
            document.getElementById(`mc-move-${i}-2`).value,
            document.getElementById(`mc-move-${i}-3`).value
        ];

        const statNames = ['hp', 'attack', 'defense', 'sp_atk', 'sp_def', 'speed'];
        statCard.evs = statCard.evs || {};
        for (const statName of statNames) {
            statCard.stats[statName] = parseInt(document.getElementById(`sc-stat-${i}-${statName}`).value) || 0;
            const evVal = parseInt(document.getElementById(`sc-ev-${i}-${statName}`).value);
            statCard.evs[statName] = isNaN(evVal) ? null : evVal;
        }
        statCard.nature = document.getElementById(`sc-nature-${i}`).value;
    }

    logMsg('正在生成队伍...');
    try {
        const res = await fetch('/api/teams/build', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(currentDraft)
        });
        const data = await res.json();
        if (data.success) {
            currentTeams['my-team'] = data.team.roster;
            renderTeam(currentTeams['my-team'], 'my-team');
            closeDraftEditor();
            logMsg('队伍已生成！');
        } else {
            logMsg(`生成失败：${data.error}`);
        }
    } catch (err) {
        logMsg(`生成错误: ${err.message}`);
    }
}

function switchEvoform(side, index, evoIndex) {
    const team = currentTeams[side];
    if (!team || !team[index]) return;

    const pokemon = team[index];
    if (!pokemon.evoforms || !pokemon.evoforms[evoIndex]) return;

    // 初始化原始数据（第一次切换时保存）
    if (!pokemon._originalData) {
        pokemon._originalData = {
            base_stats: pokemon.base_stats,
            stats: pokemon.stats,
            ability: pokemon.ability,
            types: pokemon.types,
            type_effectiveness: pokemon.type_effectiveness,
            sprite: pokemon.sprite,
            slug:pokemon.slug
        };
    }

    // 如果再点一次同一个按钮，退回原始形态
    if (pokemon._currentEvoIndex === evoIndex) {
        pokemon.base_stats = pokemon._originalData.base_stats;
        pokemon.stats = pokemon._originalData.stats;
        pokemon.ability = pokemon._originalData.ability;
        pokemon.types = pokemon._originalData.types;
        pokemon.type_effectiveness = pokemon._originalData.type_effectiveness;
        pokemon.sprite = pokemon._originalData.sprite;
        pokemon.slug = pokemon._originalData.slug;
        pokemon._currentEvoIndex = -1;
    } else {
        // 切换到新的 evoform
        const evo = pokemon.evoforms[evoIndex];
        pokemon.base_stats = evo.base_stats;
        pokemon.stats = evo.stats;
        pokemon.ability = evo.ability || pokemon._originalData.ability;
        pokemon.types = evo.types;
        pokemon.type_effectiveness = evo.type_effectiveness;
        pokemon.sprite = evo.sprite;
        pokemon.slug = evo.slug_name;
        pokemon._currentEvoIndex = evoIndex;
    }

    renderTeam(team, side);
    const overlay = document.getElementById('move-damage-overlay');
    if (overlay && overlay.classList.contains('open') && activeDamageQuery) {
        showMoveDamageRange(activeDamageQuery.side, activeDamageQuery.pokemonIndex, activeDamageQuery.moveIndex);
    }
    if (typeof showDamageInfo === 'function') showDamageInfo();
    if (typeof showDamageInfoDetail === 'function') showDamageInfoDetail();
}

async function generateOpponentTeam() {
    document.querySelectorAll('.menu-item.active').forEach(m => m.classList.remove('active'));
    logMsg('正在生成对方队伍。请等待。');
    const res = await fetch('/api/teams/generate-opponent', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
        buildOppTeamVariants(data);
        // 新对手队伍加载后，清空旧拖拽偏移，避免同槽位继承历史位置。
        resetOppSpeedMarkerRatio();
        renderTeam(currentTeams['opp-team'], 'opp-team');
        logMsg(`对方队伍已生成${data.matched_teams && data.matched_teams.length ? `，已匹配 ${data.matched_teams.length} 个队伍` : ''}`);
        if (typeof showDamageInfo === 'function') showDamageInfo();
        if (typeof showDamageInfoDetail === 'function') showDamageInfoDetail();
        boostState = {
            my: {},
            opp: {}
        };
        
    } else {
        logMsg(`生成失败：${data.error}`);
    }
}

function buildOppTeamVariants(data, keepCurrent = false) {
    const matched = data.matched_teams || [];
    if (keepCurrent) {
        // 手动修正后重新匹配：保留当前展示的队伍作为第 0 个，停留在当前
        const current = currentTeams['opp-team'] || [];
        oppTeamVariants = [{ label: '当前', date: '', roster: current }];
        oppTeamVariantIndex = 0;
    } else {
        // 首次生成：第 0 个为对战数据组装的队伍，有匹配时默认选第一个匹配队伍
        oppTeamVariants = [{ label: '对战数据', date: '', roster: data.team.roster || [] }];
        oppTeamVariantIndex = oppTeamVariants.length > 1 ? 1 : 0;
    }
    matched.forEach((m) => {
        oppTeamVariants.push({
            label: m.title || m.team_id,
            date: m.date_shared || '',
            roster: (m.team && m.team.roster) || [],
        });
    });
    currentTeams['opp-team'] = oppTeamVariants[oppTeamVariantIndex].roster;
    renderOppTeamSwitcher();
}

function renderOppTeamSwitcher() {
    const el = document.getElementById('opp-team-switcher');
    if (!el) return;
    if (!oppTeamVariants || oppTeamVariants.length <= 1) {
        el.style.display = 'none';
        return;
    }
    el.style.display = '';
    const count = document.getElementById('opp-team-count');
    if (count) count.textContent = `(${oppTeamVariantIndex + 1}/${oppTeamVariants.length})`;
    const pickerCount = document.getElementById('opp-team-picker-count');
    if (pickerCount) pickerCount.textContent = `(${oppTeamVariantIndex + 1}/${oppTeamVariants.length})`;
}

function switchOppTeamVariant(i) {
    if (!oppTeamVariants || !oppTeamVariants[i]) return;
    oppTeamVariantIndex = i;
    currentTeams['opp-team'] = oppTeamVariants[i].roster;
    resetOppSpeedMarkerRatio();
    renderTeam(currentTeams['opp-team'], 'opp-team');
    renderOppTeamSwitcher();
    const overlay = document.getElementById('opp-team-picker-overlay');
    if (overlay && overlay.classList.contains('open')) renderOppTeamPickerBody();
    if (typeof showDamageInfo === 'function') showDamageInfo();
    if (typeof showDamageInfoDetail === 'function') showDamageInfoDetail();
}

function pickerTextOf(value) {
    if (!value) return '';
    if (Array.isArray(value)) return value.map(v => pickerTextOf(v)).filter(Boolean).join(', ');
    if (typeof value === 'object') return value.name_zh || value.name || '';
    return String(value);
}

const _NATURE_ARROW_ZH = {
    'attack↑/defense↓': '寂寞',
    'attack↑/speed↓': '勇敢',
    'attack↑/sp_atk↓': '固执',
    'attack↑/sp_def↓': '调皮',
    'defense↑/attack↓': '大胆',
    'defense↑/speed↓': '悠闲',
    'defense↑/sp_atk↓': '淘气',
    'defense↑/sp_def↓': '乐天',
    'speed↑/attack↓': '胆小',
    'speed↑/defense↓': '急躁',
    'speed↑/sp_atk↓': '爽朗',
    'speed↑/sp_def↓': '天真',
    'sp_atk↑/attack↓': '内敛',
    'sp_atk↑/defense↓': '慢吞吞',
    'sp_atk↑/speed↓': '冷静',
    'sp_atk↑/sp_def↓': '马虎',
    'sp_def↑/attack↓': '温和',
    'sp_def↑/defense↓': '温顺',
    'sp_def↑/speed↓': '自大',
    'sp_def↑/sp_atk↓': '慎重',
};

function natureArrowToZh(arrow) {
    if (!arrow) return '';
    return _NATURE_ARROW_ZH[arrow] || arrow;
}

function renderPickerEvs(evs) {
    const labels = [
        { key: 'hp', label: 'HP' },
        { key: 'attack', label: 'A' },
        { key: 'defense', label: 'D' },
        { key: 'sp_atk', label: 'SA' },
        { key: 'sp_def', label: 'SD' },
        { key: 'speed', label: 'S' },
    ];
    if (!evs || !Object.keys(evs).length) return '<div class="opp-team-picker-meta">无</div>';
    const rows = labels.filter(({ key }) => (evs[key] ?? 0) !== 0)
        .map(({ key, label }) =>
            `<div class="opp-team-picker-ev"><span>${label}</span><span>${evs[key]}</span></div>`);
    return rows.length ? rows.join('') : '<div class="opp-team-picker-meta">无</div>';
}

function renderPickerPokemonCard(pokemon) {
    if (!pokemon) return '<div class="opp-team-picker-card"></div>';
    const spritePath = (pokemon.sprite || '').replace(/^sprites\//, '');
    const spriteHtml = spritePath
        ? `<img class="opp-team-picker-sprite" src="/sprites/${spritePath}" alt="">`
        : '<div class="opp-team-picker-sprite"></div>';
    const nameZh = pokemon.name_zh || pokemon.name || '';
    const nature = natureArrowToZh(pokemon.nature) || '-';
    const item = pickerTextOf(pokemon.held_item) || '无道具';
    const ability = pickerTextOf(pokemon.ability) || '-';
    const moves = (pokemon.moves || []).map(m => {
        const typeKey = String(m.type || 'normal').toLowerCase();
        const title = (m.short_effect_zh || m.short_effect || '').replace(/"/g, '&quot;');
        const name = m.name_zh || m.name || '';
        return `<div class="opp-team-picker-move type-${typeKey}" title="${title}">${renderTypeIcon(m.type, 'opp-team-picker-move-icon')}<span class="opp-team-picker-move-name">${name}</span></div>`;
    }).join('') || '<div class="opp-team-picker-move type-normal"><span class="opp-team-picker-move-name">-</span></div>';
    return `
        <div class="opp-team-picker-card">
            <div class="opp-team-picker-card-left">
                ${spriteHtml}
                <div class="opp-team-picker-name" title="${nameZh}">${nameZh}</div>
                <div class="opp-team-picker-meta" title="${nature}">${nature}</div>
                <div class="opp-team-picker-meta" title="${item}">${item}</div>
                <div class="opp-team-picker-meta" title="${ability}">${ability}</div>
            </div>
            <div class="opp-team-picker-card-right">
                ${moves}
            </div>
            <div class="opp-team-picker-evs">
                ${renderPickerEvs(pokemon.evs)}
            </div>
        </div>`;
}

function sortPokemonByDex(roster) {
    // 弹窗内统一按图鉴号升序排列，便于跨队伍对照（不修改原始队伍）
    return [...(roster || [])].sort((a, b) =>
        (Number(a.index) || 0) - (Number(b.index) || 0) || (a.slug || '').localeCompare(b.slug || ''));
}

function renderOppTeamPickerBody() {
    const body = document.getElementById('opp-team-picker-body');
    if (!body) return;
    if (!oppTeamVariants || !oppTeamVariants.length) {
        body.innerHTML = '<div class="opp-team-picker-empty">暂无匹配队伍</div>';
        return;
    }
    body.innerHTML = oppTeamVariants.map((v, i) => `
        <div class="opp-team-picker-row ${i === oppTeamVariantIndex ? 'active' : ''}" onclick="switchOppTeamVariant(${i})">
            <div class="opp-team-picker-row-header">
                <span class="opp-team-picker-row-name">${v.label}</span>
                ${v.date ? `<span class="opp-team-picker-row-date">${v.date}</span>` : ''}
            </div>
            <div class="opp-team-picker-cards">
                ${sortPokemonByDex(v.roster).map(pokemon => renderPickerPokemonCard(pokemon)).join('')}
            </div>
        </div>
    `).join('');
}

function openOppTeamPicker() {
    if (!oppTeamVariants || oppTeamVariants.length <= 1) return;
    const overlay = document.getElementById('opp-team-picker-overlay');
    if (!overlay) return;
    renderOppTeamPickerBody();
    renderOppTeamSwitcher();
    overlay.classList.add('open');
}

function closeOppTeamPicker() {
    const overlay = document.getElementById('opp-team-picker-overlay');
    if (overlay) overlay.classList.remove('open');
}

async function reMatchOpponentTeam() {
    const slugs = (currentTeams['opp-team'] || []).map(p => p.slug).filter(Boolean);
    if (!slugs.length) return;
    try {
        const res = await fetch('/api/teams/match-opponent', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slugs })
        });
        const data = await res.json();
        if (data.success) {
            buildOppTeamVariants(data, true);
            resetOppSpeedMarkerRatio();
            renderTeam(currentTeams['opp-team'], 'opp-team');
            const matchedCount = (data.matched_teams || []).length;
            logMsg(matchedCount ? `手动修正后已重新匹配：${matchedCount} 个队伍` : '手动修正后未匹配到已收录队伍');
            if (typeof showDamageInfo === 'function') showDamageInfo();
            if (typeof showDamageInfoDetail === 'function') showDamageInfoDetail();
        } else {
            logMsg(`重新匹配失败：${data.error}`);
        }
    } catch (err) {
        logMsg(`重新匹配错误: ${err.message}`);
    }
}

function openPokemonSwitcher(side, index) {
    let overlay = document.getElementById('pokemon-switcher-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'pokemon-switcher-overlay';
        overlay.className = 'pokemon-switcher-overlay';
        document.body.appendChild(overlay);
    }

    overlay.dataset.side = side;
    overlay.dataset.index = index;

    const currentPoke = currentTeams[side]?.[index];
    const currentSlug = currentPoke?.slug || '';
    const currentNameZh = currentPoke?.name_zh || '';

    overlay.innerHTML = `
        <div class="pokemon-switcher-box">
            <div class="pokemon-switcher-header">
                <span>切换宝可梦 — ${currentNameZh} (位置 ${index + 1})</span>
                <button class="pokemon-switcher-close" onclick="closePokemonSwitcher()">×</button>
            </div>
            <div class="pokemon-switcher-body">
                <div class="pokemon-switcher-field">
                    <label>中文名</label>
                    <div style="display:flex;gap:4px">
                        <input type="text" id="ps-name-zh" placeholder="输入中文名..." value="${currentNameZh}" />
                        <button id="ps-search-btn" class="ps-btn">查询</button>
                    </div>
                </div>
                <div class="pokemon-switcher-field">
                    <label>形态</label>
                    <select id="ps-form">
                        <option value="">-- 选择 --</option>
                    </select>
                </div>
                <div class="pokemon-switcher-field">
                    <label>Slug</label>
                    <input type="text" id="ps-slug" value="${currentSlug}" readonly />
                </div>
                <div class="pokemon-switcher-info" id="ps-info"></div>
            </div>
            <div class="pokemon-switcher-footer">
                <button class="ps-btn ps-btn-cancel" onclick="closePokemonSwitcher()">取消</button>
                <button class="ps-btn ps-btn-confirm" id="ps-confirm-btn">确认更新</button>
            </div>
        </div>
    `;

    // Enter key triggers search
    document.getElementById('ps-name-zh').addEventListener('keydown', (e) => {
        if (e.key === 'Enter') document.getElementById('ps-search-btn').click();
    });

    document.getElementById('ps-search-btn').onclick = async () => {
        const nameZh = document.getElementById('ps-name-zh').value.trim();
        if (!nameZh) { document.getElementById('ps-info').textContent = '请输入中文名'; return; }
        try {
            const res = await fetch(`/api/pokemon/by-name-zh/${encodeURIComponent(nameZh)}`);
            const data = await res.json();
            if (data.success) {
                const formSelect = document.getElementById('ps-form');
                formSelect.innerHTML = '<option value="">-- 选择形态 --</option>';
                data.variants.forEach(v => {
                    const opt = document.createElement('option');
                    opt.value = v.slug;
                    opt.textContent = v.form || '(默认)';
                    formSelect.appendChild(opt);
                });
                if (data.variants.length > 0) {
                    formSelect.value = data.variants[0].slug;
                    document.getElementById('ps-slug').value = data.variants[0].slug;
                }
                document.getElementById('ps-info').textContent = `找到 ${data.variants.length} 个形态`;
            } else {
                document.getElementById('ps-info').textContent = `未找到: ${nameZh}`;
            }
        } catch (err) {
            document.getElementById('ps-info').textContent = `查询失败: ${err.message}`;
        }
    };

    document.getElementById('ps-form').onchange = () => {
        const slug = document.getElementById('ps-form').value;
        document.getElementById('ps-slug').value = slug;
    };

    document.getElementById('ps-confirm-btn').onclick = async () => {
        const slug = document.getElementById('ps-slug').value;
        if (!slug) { document.getElementById('ps-info').textContent = '请先查询并选择宝可梦'; return; }
        document.getElementById('ps-confirm-btn').disabled = true;
        document.getElementById('ps-confirm-btn').textContent = '更新中...';
        await rebuildPokemon(side, index, slug);
        closePokemonSwitcher();
    };

    overlay.classList.add('open');
}

function closePokemonSwitcher() {
    const overlay = document.getElementById('pokemon-switcher-overlay');
    if (overlay) overlay.classList.remove('open');
}

async function rebuildPokemon(side, index, slug) {
    try {
        const res = await fetch('/api/pokemon/rebuild', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ slug })
        });
        const data = await res.json();
        if (data.success) {
            currentTeams[side][index] = data.pokemon;
            renderTeam(currentTeams[side], side);
            logMsg(`已更新 ${data.pokemon.name_zh || data.pokemon.name}`);
            if (typeof showDamageInfo === 'function') showDamageInfo();
            if (typeof showDamageInfoDetail === 'function') showDamageInfoDetail();
            const overlay = document.getElementById('move-damage-overlay');
            if (overlay && overlay.classList.contains('open') && activeDamageQuery) {
                showMoveDamageRange(activeDamageQuery.side, activeDamageQuery.pokemonIndex, activeDamageQuery.moveIndex);
            }
            // 手动修正对方宝可梦后，用最新 6 只重新匹配已收录队伍
            if (side === 'opp-team') {
                reMatchOpponentTeam();
            }
        } else {
            logMsg(`更新失败：${data.error}`);
        }
    } catch (err) {
        logMsg(`更新错误: ${err.message}`);
    }
}

function toggleSpeedFade(side, index) {
    if (side === 'my') {
        const sprite = document.querySelector(`.speed-my-sprite[data-pokemon-index="${index}"]`);
        const allTicks = document.querySelectorAll('.speed-tick.speed-my-tick');
        const tick = allTicks[index];

        const isFaded = fadedElements.my.has(index);
        if (isFaded) {
            fadedElements.my.delete(index);
            if (sprite) sprite.style.opacity = '1';
            if (tick) tick.style.opacity = '1';
        } else {
            fadedElements.my.add(index);
            if (sprite) sprite.style.opacity = '0.3';
            if (tick) tick.style.opacity = '0.3';
        }
    } else if (side === 'opp') {
        const row = document.querySelector(`.speed-opp-row[data-pokemon-index="${index}"]`);
        const isFaded = fadedElements.opp.has(index);
        if (isFaded) {
            fadedElements.opp.delete(index);
            if (row) row.style.opacity = '1';
        } else {
            fadedElements.opp.add(index);
            if (row) row.style.opacity = '0.3';
        }
    }
}

function renderSpeedAxis() {
    const maxSpeed = getDynamicMaxSpeed();
    renderSpeedAxisTicks(maxSpeed);

    // 我方：sprite 画在轴上
    const myContainer = document.getElementById('speed-markers-my');
    if (myContainer) {
        myContainer.innerHTML = '';
        (currentTeams['my-team'] || []).forEach((p, index) => {
            const speed = p.stats && p.stats.speed != null ? p.stats.speed : 0;
            const scarf = isChoiceScarf(p);
            const spdBoost = (boostState.my[p.index] || {}).spe || 0;
            const effectiveSpeed = getEffectiveSpeed(speed, speedFieldState.my_tailwind, scarf, spdBoost);
            const pct = speedToPercent(effectiveSpeed, maxSpeed);
            const label = p.name_zh || p.name || '?';
            const spritePath = p.sprite ? p.sprite.replace(/^sprites\//, '') : '';
            const speedLabel = scarf ? `围巾${effectiveSpeed}` : `速${effectiveSpeed}`;

            // 图标
            const spriteEl = document.createElement('div');
            spriteEl.className = 'speed-my-sprite';
            spriteEl.dataset.pokemonIndex = index;
            spriteEl.style.left = `${pct}%`;
            spriteEl.style.cursor = 'pointer';
            spriteEl.title = `${label}: ${speedLabel}`;
            if (spritePath) spriteEl.style.backgroundImage = `url('/sprites/${spritePath}')`;
            spriteEl.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleSpeedFade('my', index);
            });
            myContainer.appendChild(spriteEl);
        });

        // 动态添加我方速度到 speed-axis-main
        const axisMain = document.getElementById('speed-axis-main');
        const existingMyTicks = axisMain.querySelectorAll('.speed-tick.speed-my-tick');
        existingMyTicks.forEach(el => el.remove());

        (currentTeams['my-team'] || []).forEach((p, index) => {
            const speed = p.stats && p.stats.speed != null ? p.stats.speed : 0;
            const scarf = isChoiceScarf(p);
            const spdBoost = (boostState.my[p.index] || {}).spe || 0;
            const effectiveSpeed = getEffectiveSpeed(speed, speedFieldState.my_tailwind, scarf, spdBoost);
            const pct = speedToPercent(effectiveSpeed, maxSpeed);
            const tickEl = document.createElement('div');
            tickEl.className = 'speed-tick speed-my-tick';
            tickEl.dataset.pokemonIndex = index;
            tickEl.style.left = `${pct}%`;
            tickEl.innerHTML = `<span>${effectiveSpeed}</span>`;
            axisMain.appendChild(tickEl);
        });
    }

    // 对方：前3在轴上方，后3在轴下方，每行一个 Pokemon（精灵 + min + bar + max）
    function fillOppSection(containerId, pokemon, startIndex) {
        const container = document.getElementById(containerId);
        if (!container) return;
        container.innerHTML = '';
        pokemon.forEach((p, i) => {
            const globalIndex = startIndex + i;
            const scarf = isChoiceScarf(p);
            const spdBoost = (boostState.opp[p.index] || {}).spe || 0;
            const spd = p.stats && p.stats.speed;
            const [baseMin, baseMax] = Array.isArray(spd) ? spd : [spd || 0, spd || 0];
            const sMin = getEffectiveSpeed(baseMin, speedFieldState.opp_tailwind, scarf, spdBoost);
            const sMax = getEffectiveSpeed(baseMax, speedFieldState.opp_tailwind, scarf, spdBoost);
            const pctMin = speedToPercent(sMin, maxSpeed);
            const pctMax = speedToPercent(sMax, maxSpeed);
            const label = p.name_zh || p.name || '?';
            const spritePath = p.sprite ? p.sprite.replace(/^sprites\//, '') : '';
            const rangeLabel = scarf ? `围巾${sMin}–${sMax}` : `速${sMin}–${sMax}`;

            const rowEl = document.createElement('div');
            rowEl.className = 'speed-opp-row';
            rowEl.dataset.pokemonIndex = globalIndex;
            rowEl.style.cursor = 'pointer';
            rowEl.title = `${label}: ${rangeLabel}`;

            // 中性性格(1.0)下的速度分界值
            const baseSpd = (p.base_stats && p.base_stats.speed) || 0;
            const neutral0EV = baseSpd + 20;           // (base + 20 + 0) * 1.0
            const neutral32EV = baseSpd + 20 + 32;     // (base + 20 + 32) * 1.0
            const sNeutral0EV = getEffectiveSpeed(neutral0EV, speedFieldState.opp_tailwind, scarf, spdBoost);
            const sNeutral32EV = getEffectiveSpeed(neutral32EV, speedFieldState.opp_tailwind, scarf, spdBoost);
            const pctNeutral0EV = speedToPercent(sNeutral0EV, maxSpeed);
            const pctNeutral32EV = speedToPercent(sNeutral32EV, maxSpeed);

            // 三段范围条：红(-10%性格) / 默认(中性性格) / 绿(+10%性格)
            const barDown = document.createElement('div');
            barDown.className = 'speed-opp-bar speed-opp-bar-down';
            barDown.style.left = `${pctMin}%`;
            barDown.style.width = `${Math.max(pctNeutral0EV - pctMin, 0.5)}%`;
            rowEl.appendChild(barDown);

            const barMid = document.createElement('div');
            barMid.className = 'speed-opp-bar speed-opp-bar-mid';
            barMid.style.left = `${pctNeutral0EV}%`;
            barMid.style.width = `${Math.max(pctNeutral32EV - pctNeutral0EV, 0.5)}%`;
            rowEl.appendChild(barMid);

            const barUp = document.createElement('div');
            barUp.className = 'speed-opp-bar speed-opp-bar-up';
            barUp.style.left = `${pctNeutral32EV}%`;
            barUp.style.width = `${Math.max(pctMax - pctNeutral32EV, 0.5)}%`;
            rowEl.appendChild(barUp);

            // 从 EV + 性格计算实际速度，自动定位精灵图标
            const ev = p.evs?.speed ?? 0;
            const natureMult = getNatureSpeedMultiplier(p.nature_en);
            const actualSpeed = Math.floor((baseSpd + 20 + ev) * natureMult);
            const sActual = getEffectiveSpeed(actualSpeed, speedFieldState.opp_tailwind, scarf, spdBoost);
            const pctActual = speedToPercent(sActual, maxSpeed);
            const defaultRatio = baseMax !== baseMin ? (actualSpeed - baseMin) / (baseMax - baseMin) : 0.5;
            const markerRatio = oppSpeedMarkerRatio[globalIndex] !== undefined
                ? clamp(oppSpeedMarkerRatio[globalIndex], 0, 1)
                : clamp(defaultRatio, 0, 1);
            const pctMid = pctMin + (pctMax - pctMin) * markerRatio;
            const spriteEl = document.createElement('div');
            spriteEl.className = 'speed-opp-sprite';
            spriteEl.dataset.pokemonIndex = globalIndex;
            spriteEl.style.left = `${pctMid}%`;
            spriteEl.style.transform = 'translate(-50%, -50%)';
            if (spritePath) spriteEl.style.backgroundImage = `url('/sprites/${spritePath}')`;
            spriteEl.style.cursor = 'pointer';
            rowEl.appendChild(spriteEl);

            // min 值（范围条前）
            const minEl = document.createElement('div');
            minEl.className = 'speed-opp-text';
            minEl.style.left = `${pctMin}%`;
            minEl.textContent = sMin;
            minEl.style.transform = 'translate(-100%, -50%)';
            rowEl.appendChild(minEl);

            // 中性性格 0EV 分界值
            const n0El = document.createElement('div');
            n0El.className = 'speed-opp-text speed-opp-text-mid';
            n0El.style.left = `${pctNeutral0EV}%`;
            n0El.textContent = sNeutral0EV;
            n0El.style.transform = 'translate(-50%, -50%)';
            rowEl.appendChild(n0El);

            // 中性性格 32EV 分界值
            const n32El = document.createElement('div');
            n32El.className = 'speed-opp-text speed-opp-text-mid';
            n32El.style.left = `${pctNeutral32EV}%`;
            n32El.textContent = sNeutral32EV;
            n32El.style.transform = 'translate(-50%, -50%)';
            rowEl.appendChild(n32El);

            // max 值（范围条后）
            const maxEl = document.createElement('div');
            maxEl.className = 'speed-opp-text';
            maxEl.style.left = `${pctMax}%`;
            maxEl.textContent = sMax;
            maxEl.style.transform = 'translateY(-50%)';
            rowEl.appendChild(maxEl);

            // 为 row、sprite、bar 添加点击事件
            const clickHandler = (e) => {
                e.stopPropagation();
                toggleSpeedFade('opp', globalIndex);
            };
            rowEl.addEventListener('click', clickHandler);
            barDown.addEventListener('click', clickHandler);
            barMid.addEventListener('click', clickHandler);
            barUp.addEventListener('click', clickHandler);
            spriteEl.addEventListener('mousedown', (event) => {
                startOppSpeedDrag(event, globalIndex, rowEl, pctMin, pctMax);
            });
            spriteEl.addEventListener('click', (event) => {
                event.stopPropagation();
            });

            container.appendChild(rowEl);
        });
    }

    const opp = currentTeams['opp-team'] || [];
    fillOppSection('speed-opp-top', opp.slice(0, 3), 0);
    fillOppSection('speed-opp-bottom', opp.slice(3, 6), 3);

    // 恢复虚化状态
    fadedElements.my.forEach(index => {
        const sprite = document.querySelector(`.speed-my-sprite[data-pokemon-index="${index}"]`);
        const allTicks = document.querySelectorAll('.speed-tick.speed-my-tick');
        const tick = allTicks[index];
        if (sprite) sprite.style.opacity = '0.3';
        if (tick) tick.style.opacity = '0.3';
    });

    fadedElements.opp.forEach(index => {
        const row = document.querySelector(`.speed-opp-row[data-pokemon-index="${index}"]`);
        if (row) row.style.opacity = '0.3';
    });
}


window.addEventListener('load', () => {
    updateTailwindButtons();
    renderSpeedAxis();
});

