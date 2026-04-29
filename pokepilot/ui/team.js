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
    opp_tailwind: false
};
let moveDamageDragState = null;
let battleMode = 'double';
let activeDamageQuery = null;


function getEffectiveSpeed(speed, hasTailwind) {
    const value = Number(speed) || 0;
    return hasTailwind ? value * 2 : value;
}


function getDynamicMaxSpeed() {
    const maxCandidates = [];

    (currentTeams['my-team'] || []).forEach((pokemon) => {
        const speed = pokemon?.stats?.speed;
        maxCandidates.push(getEffectiveSpeed(speed, speedFieldState.my_tailwind));
    });

    (currentTeams['opp-team'] || []).forEach((pokemon) => {
        const speed = pokemon?.stats?.speed;
        if (Array.isArray(speed)) {
            maxCandidates.push(getEffectiveSpeed(speed[0], speedFieldState.opp_tailwind));
            maxCandidates.push(getEffectiveSpeed(speed[1], speedFieldState.opp_tailwind));
        } else {
            maxCandidates.push(getEffectiveSpeed(speed, speedFieldState.opp_tailwind));
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


function renderCard(pokemon, side, index) {
    const inner = document.createElement('div');
    inner.className = 'card-inner';
    const spritePath = pokemon.sprite.replace(/^sprites\//, '');

    // 属性徽标
    const typeIcons = pokemon.types.map(t => {
        const typeId = TYPE_ID_MAP[t] || 1;
        return `<div class="type-icon" style="background-image: url('/sprites/sprites/types/generation-ix/scarlet-violet/small/${typeId}.png')"></div>`;
    }).join('');

    // 处理 ability - 统一为列表格式，每个分别带 hover
    let abilityHtml = '';
    if (pokemon.ability && Array.isArray(pokemon.ability) && pokemon.ability.length > 0) {
        abilityHtml = pokemon.ability.map(a => {
            const name = a.name_zh || a.name || '';
            const pctStr = a.pct ? ` (${Math.round(a.pct * 100)}%)` : '';
            const desc = a.description_zh || a.description || '';
            const title = `${name}${pctStr}\n${desc}`;
            return `<span class="card-ability" title="${title.replace(/"/g, '&quot;')}">${name}</span>`;
        }).join(', ');
    }

    // 处理 held_item - 统一为列表格式，每个分别带 hover
    let itemHtml = '';
    if (pokemon.held_item && Array.isArray(pokemon.held_item) && pokemon.held_item.length > 0) {
        itemHtml = pokemon.held_item.map(i => {
            const name = i.name_zh || i.name || '';
            const pctStr = i.pct ? ` (${Math.round(i.pct * 100)}%)` : '';
            const desc = i.description_zh || i.description || '';
            const title = `${name}${pctStr}\n${desc}`;
            return `<span class="card-item" title="${title.replace(/"/g, '&quot;')}">${name}</span>`;
        }).join(', ');
    }

    // 进化形态按钮
    let evoButtonsHtml = '';
    if (pokemon.evoforms && pokemon.evoforms.length > 0) {
        evoButtonsHtml = pokemon.evoforms.map((evo, evoIdx) => {
            const buttonName = evo.form_name || 'mega';
            const isActive = pokemon._currentEvoIndex === evoIdx ? 'active' : '';
            return `<button class="evo-button ${isActive}" onclick="switchEvoform('${side}', ${index}, ${evoIdx})" title="切换至 ${buttonName}">${buttonName}</button>`;
        }).join('');
    }

    // 招式（用属性颜色作为背景，显示威力/准确度）
    const moves = pokemon.moves.map((m, moveIdx) => {
        const powerAccuracy = m.power !== null ? `${m.power}/${m.accuracy ?? '-'}` : '-/-';
        const priorityText = Number(m.priority || 0) !== 0 ? ` P${Number(m.priority) >= 0 ? '+' : ''}${m.priority}` : '';
        const desc = m.short_effect_zh || m.short_effect || '';
        const pctStr = m.pct ? `使用率: ${Math.round(m.pct * 100)}%` : '';
        const moveTitle = [desc, pctStr].filter(Boolean).join('\n');
        const moveName = m.name_zh || m.name || '';
        const clickableClass = (side === 'my-team' || side === 'opp-team') ? ' clickable' : '';
        const clickAttr = (side === 'my-team' || side === 'opp-team')
            ? ` onclick="showMoveDamageRange('${side}', ${index}, ${moveIdx})"`
            : '';
        return `<div class="move-chip type-${m.type.toLowerCase()}${clickableClass}" title="${moveTitle.replace(/"/g, '&quot;')}"${clickAttr}>${moveName}<span class="move-stats">${powerAccuracy}${priorityText}</span></div>`;
    }).join('');

    // Stats barplot 显示
    const stats = pokemon.stats;
    const baseStats = pokemon.base_stats;
    const statLabels = [
        { key: 'hp', label: 'HP' },
        { key: 'attack', label: 'A' },
        { key: 'defense', label: 'D' },
        { key: 'sp_atk', label: 'SA' },
        { key: 'sp_def', label: 'SD' },
        { key: 'speed', label: 'S' }
    ];

    // 解析 nature
    let upStat = '', downStat = '';
    if (pokemon.nature) {
        const [up, down] = pokemon.nature.split('/');
        upStat = up ? up.split('↑')[0] : '';
        downStat = down ? down.split('↓')[0] : '';
    }

    const statsHtml = statLabels.map(({ key, label }) => {
        const base = baseStats[key];
        const current = stats[key];
        const barWidth = Math.round((base / 180) * 100);
        let labelClass = '';
        if (upStat && upStat.toLowerCase() === key.toLowerCase()) labelClass = 'nature-up';
        else if (downStat && downStat.toLowerCase() === key.toLowerCase()) labelClass = 'nature-down';
        return `
            <div class="stat-row">
                <span class="stat-label ${labelClass}">${label}</span>
                <div class="stat-bar-container">
                    <div class="stat-bar" style="width: ${barWidth}%"></div>
                </div>
                <span class="stat-value ${labelClass}">${base}(${current})</span>
            </div>
        `;
    }).join('');

    // 属性相克 - 分类显示
    const effectiveness = pokemon.type_effectiveness;

    const immunity = Object.entries(effectiveness)
        .filter(([, mult]) => mult === 0.0)
        .map(([type]) => {
            const typeId = TYPE_ID_MAP[type.charAt(0).toUpperCase() + type.slice(1)] || 1;
            const typeTitle = type.charAt(0).toUpperCase() + type.slice(1);
            return `<div class="type-icon-small" title="${typeTitle}" style="background-image: url('/sprites/sprites/types/generation-ix/scarlet-violet/small/${typeId}.png')"></div>`;
        }).join('');

    const resistQuarter = Object.entries(effectiveness)
        .filter(([, mult]) => mult === 0.25)
        .map(([type]) => {
            const typeId = TYPE_ID_MAP[type.charAt(0).toUpperCase() + type.slice(1)] || 1;
            const typeTitle = type.charAt(0).toUpperCase() + type.slice(1);
            return `<div class="type-icon-small" title="${typeTitle}" style="background-image: url('/sprites/sprites/types/generation-ix/scarlet-violet/small/${typeId}.png')"></div>`;
        }).join('');

    const superEffectiveX4 = Object.entries(effectiveness)
        .filter(([, mult]) => mult === 4.0)
        .map(([type]) => {
            const typeId = TYPE_ID_MAP[type.charAt(0).toUpperCase() + type.slice(1)] || 1;
            const typeTitle = type.charAt(0).toUpperCase() + type.slice(1);
            return `<div class="type-icon-small" title="${typeTitle}" style="background-image: url('/sprites/sprites/types/generation-ix/scarlet-violet/small/${typeId}.png')"></div>`;
        }).join('');

    const resistHalf = Object.entries(effectiveness)
        .filter(([, mult]) => mult === 0.5)
        .map(([type]) => {
            const typeId = TYPE_ID_MAP[type.charAt(0).toUpperCase() + type.slice(1)] || 1;
            const typeTitle = type.charAt(0).toUpperCase() + type.slice(1);
            return `<div class="type-icon-small" title="${typeTitle}" style="background-image: url('/sprites/sprites/types/generation-ix/scarlet-violet/small/${typeId}.png')"></div>`;
        }).join('');

    const superEffectiveX2 = Object.entries(effectiveness)
        .filter(([, mult]) => mult === 2.0)
        .map(([type]) => {
            const typeId = TYPE_ID_MAP[type.charAt(0).toUpperCase() + type.slice(1)] || 1;
            const typeTitle = type.charAt(0).toUpperCase() + type.slice(1);
            return `<div class="type-icon-small" title="${typeTitle}" style="background-image: url('/sprites/sprites/types/generation-ix/scarlet-violet/small/${typeId}.png')"></div>`;
        }).join('');

    // 构建有内容的行
      const firstRowHtml = superEffectiveX4 || resistQuarter || immunity ? `
        ${superEffectiveX4 ? `<span class="effectiveness-label">×4:</span>${superEffectiveX4}` : ''}
        ${resistQuarter ? `<span class="effectiveness-label">÷4:</span>${resistQuarter}` : ''}
        ${immunity ? `<span class="effectiveness-label">×0:</span>${immunity}` : ''}
    ` : '';

    const secondRowHtml = resistHalf ? `
        <span class="effectiveness-label">÷2:</span>${resistHalf}
    ` : '';

    const thirdRowHtml = superEffectiveX2 ? `
        <span class="effectiveness-label">×2:</span>${superEffectiveX2}
    ` : '';

    inner.innerHTML = `
        <div class="card-bg-sprite" style="background-image: url('/sprites/${spritePath}')"></div>
        <div class="card-info">
            <div class="card-info-left">
                <div class="card-header-section">
                    <div class="card-header">
                        <div class="card-types">${typeIcons}</div>
                        <span class="card-name">${pokemon.name_zh || pokemon.name || ''}</span>
                        ${evoButtonsHtml ? `<div class="evo-buttons">${evoButtonsHtml}</div>` : ''}
                    </div>
                    <div class="card-meta">
                        ${itemHtml || '<span class="card-item" title="">无道具</span>'}
                    </div>
                    <div class="card-meta">
                        ${abilityHtml}
                    </div>
                </div>
                <div class="card-stats-section">
                    <div class="card-stats">${statsHtml}</div>
                </div>
            </div>
            <div class="card-info-right">
                <div class="card-effectiveness-section">
                    <div class="card-effectiveness">
                        ${firstRowHtml ? `<div class="effectiveness-row">${firstRowHtml}</div>` : ''}
                        ${secondRowHtml ? `<div class="effectiveness-row">${secondRowHtml}</div>` : ''}
                        ${thirdRowHtml ? `<div class="effectiveness-row">${thirdRowHtml}</div>` : ''}
                    </div>
                </div>
                <div class="card-moves-section">
                    <div class="card-moves">${moves}</div>
                </div>
            </div>
        </div>`;
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


async function showMoveDamageRange(side, pokemonIndex, moveIndex) {
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

    try {
        const response = await fetch('/api/damage/range', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                attacker: attacker,
                move_index: moveIndex,
                opp_team: targetTeam,
                battle_mode: battleMode
            })
        });
        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
            const text = await response.text();
            content.textContent = `接口返回非JSON（HTTP ${response.status}）：${text.slice(0, 120)}`;
            return;
        }
        const data = await response.json();
        if (!data.success) {
            content.textContent = `计算失败：${data.error || 'unknown'}`;
            return;
        }
        if (Number(data.move_priority || 0) !== 0) {
            const p = Number(data.move_priority);
            title.textContent += `（先制度 ${p >= 0 ? '+' : ''}${p}）`;
        }
        if (data.battle_mode === 'double' && data.is_spread_move) {
            title.textContent += '（双打范围修正）';
        }
        if (data.is_guaranteed_critical) {
            title.textContent += '（必定要害修正）';
        }
        if (data.is_multi_hit) {
            title.textContent += '（多段技能，当前为单段伤害）';
        }
        renderMoveDamageRows(data.rows || []);
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
            statsRow.appendChild(statGroup);
        }
        fields.appendChild(statsRow);

        const natureGroup = createFieldGroup('性格', `sc-nature-${i}`, statCard.nature || '', false);
        natureGroup.style.gridColumn = '1 / -1';
        fields.appendChild(natureGroup);

        slot.appendChild(sprite);
        slot.appendChild(fields);
        panel.appendChild(slot);
        panels.appendChild(panel);
    }

    overlay.classList.add('open');
}

function createFieldGroup(label, inputId, value, readonly, type = 'text') {
    const group = document.createElement('div');
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
        for (const statName of statNames) {
            statCard.stats[statName] = parseInt(document.getElementById(`sc-stat-${i}-${statName}`).value) || 0;
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
            sprite: pokemon.sprite
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
        pokemon._currentEvoIndex = evoIndex;
    }

    renderTeam(team, side);
    const overlay = document.getElementById('move-damage-overlay');
    if (overlay && overlay.classList.contains('open') && activeDamageQuery) {
        showMoveDamageRange(activeDamageQuery.side, activeDamageQuery.pokemonIndex, activeDamageQuery.moveIndex);
    }
}

async function generateOpponentTeam() {
    document.querySelectorAll('.menu-item.active').forEach(m => m.classList.remove('active'));
    logMsg('正在生成对方队伍。请等待。');
    const res = await fetch('/api/teams/generate-opponent', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
        currentTeams['opp-team'] = data.team.roster;
        // 新对手队伍加载后，清空旧拖拽偏移，避免同槽位继承历史位置。
        resetOppSpeedMarkerRatio();
        renderTeam(currentTeams['opp-team'], 'opp-team');
        logMsg(`对方队伍已生成`);
    } else {
        logMsg(`生成失败：${data.error}`);
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
            const effectiveSpeed = getEffectiveSpeed(speed, speedFieldState.my_tailwind);
            const pct = speedToPercent(effectiveSpeed, maxSpeed);
            const label = p.name_zh || p.name || '?';
            const spritePath = p.sprite ? p.sprite.replace(/^sprites\//, '') : '';

            // 图标
            const spriteEl = document.createElement('div');
            spriteEl.className = 'speed-my-sprite';
            spriteEl.dataset.pokemonIndex = index;
            spriteEl.style.left = `${pct}%`;
            spriteEl.style.cursor = 'pointer';
            spriteEl.title = `${label}: ${effectiveSpeed}${speedFieldState.my_tailwind ? ` (${speed}×2)` : ''}`;
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
            const effectiveSpeed = getEffectiveSpeed(speed, speedFieldState.my_tailwind);
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
            const spd = p.stats && p.stats.speed;
            const [baseMin, baseMax] = Array.isArray(spd) ? spd : [spd || 0, spd || 0];
            const sMin = getEffectiveSpeed(baseMin, speedFieldState.opp_tailwind);
            const sMax = getEffectiveSpeed(baseMax, speedFieldState.opp_tailwind);
            const pctMin = speedToPercent(sMin, maxSpeed);
            const pctMax = speedToPercent(sMax, maxSpeed);
            const label = p.name_zh || p.name || '?';
            const spritePath = p.sprite ? p.sprite.replace(/^sprites\//, '') : '';

            const rowEl = document.createElement('div');
            rowEl.className = 'speed-opp-row';
            rowEl.dataset.pokemonIndex = globalIndex;
            rowEl.style.cursor = 'pointer';
            rowEl.title = `${label}: ${sMin}–${sMax}${speedFieldState.opp_tailwind ? ` (${baseMin}-${baseMax}×2)` : ''}`;

            // 范围条
            const barEl = document.createElement('div');
            barEl.className = 'speed-opp-bar';
            barEl.style.left = `${pctMin}%`;
            barEl.style.width = `${Math.max(pctMax - pctMin, 0.5)}%`;
            rowEl.appendChild(barEl);

            // 精灵图标（bar 中间）
            const markerRatio = clamp(oppSpeedMarkerRatio[globalIndex] ?? 0.5, 0, 1);
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
            barEl.addEventListener('click', clickHandler);
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

// ===== 查看伤害克制关系=====
function viewTypeEffectiveness(){
    const overlay = document.getElementById('type-effect-overlay');
    const myRows = document.getElementById('my-effect-rows');
    const oppRows = document.getElementById('opp-effect-rows');

    // 清空旧内容
    myRows.innerHTML = '';
    oppRows.innerHTML = '';

    const myTeam = currentTeams['my-team'] || [];
    const oppTeam = currentTeams['opp-team'] || [];

    // 我方侧：表头（对方6只宝可梦头像）
    const myHeader = document.createElement('div');
    myHeader.className = 'effect-header';
    myHeader.innerHTML = `
        <div class="effect-avatar-placeholder"></div>
        <div class="effect-moves-placeholder"></div>
        <div class="effect-damage-header">
            ${oppTeam.map((oppPokemon, idx) => {
                if (!oppPokemon) return '<div class="effect-damage-item-header"></div>';
                const spritePath = oppPokemon.sprite ? oppPokemon.sprite.replace(/^sprites\//, '') : '';
                const pokemonName = oppPokemon.name_zh || oppPokemon.name || '?';
                return `<div class="effect-damage-item-header" title="${pokemonName}">
                    <img src="/sprites/${spritePath}" alt="${pokemonName}">
                    <span>${pokemonName}</span>
                </div>`;
            }).join('')}
        </div>
    `;
    myRows.appendChild(myHeader);

    // 渲染我方6行
    for (let i = 0; i < 6; i++) {
        const myPokemon = myTeam[i];
        const row = document.createElement('div');
        row.className = 'effect-row';

        if (!myPokemon) {
            row.innerHTML = `<div class="effect-row-empty">我方 ${i+1}</div>`;
        } else {
            const spritePath = myPokemon.sprite ? myPokemon.sprite.replace(/^sprites\//, '') : '';
            const pokemonName = myPokemon.name_zh || myPokemon.name || '?';

            // 左侧头像
            const avatarHtml = `
                <div class="effect-avatar">
                    ${spritePath ? `<img src="/sprites/${spritePath}" alt="${pokemonName}">` : ''}
                    <div class="effect-pokemon-name">${pokemonName}</div>
                </div>
            `;

            // 中间技能列表
            const movesHtml = `
                <div class="effect-moves">
                    ${(myPokemon.moves || []).map(m => {
                        const moveName = m.name_zh || m.name || '';
                        const moveType = m.type || '';
                        const typeId = TYPE_ID_MAP[moveType] || 1;
                        const power = m.power !== null ? m.power : '-';
                        const accuracy = m.accuracy !== null ? m.accuracy : '-';
                        return `<div class="effect-move-chip type-${moveType.toLowerCase()}" title="${moveType}">
                            <span class="move-name">${moveName}</span>
                            <div class="type-icon-mini" style="background-image: url('/sprites/sprites/types/generation-ix/scarlet-violet/small/${typeId}.png')"></div>
                            <span class="move-stats-mini">${power}/${accuracy}</span>
                        </div>`;
                    }).join('') || '<div class="effect-move-empty">无技能</div>'}
                </div>
            `;

            // 右侧伤害列表(对对方6只宝可梦) - 每个技能一行
            const damageHtml = `
                <div class="effect-damage-grid">
                    ${(myPokemon.moves || []).map(m => {
                        const moveType = (m.type || '').toLowerCase();
                        const power = m.power;
                        const moveName = m.name_zh || m.name || '';
                        return `<div class="effect-damage-row" title="${moveName}">
                            ${oppTeam.map(oppPokemon => {
                                if (!oppPokemon) return '<div class="effect-damage-cell">-</div>';
                                if (power === 0 || power === null) return '<div class="effect-damage-cell"><span class="effect-damage-placeholder"></span></div>';
                                const oppName = oppPokemon.name_zh || oppPokemon.name || '?';
                                const effectiveness = oppPokemon.type_effectiveness || {};
                                const mult = effectiveness[moveType] !== undefined ? effectiveness[moveType] : 1;
                                let cls = 'dmg-normal';
                                if (mult === 0) cls = 'dmg-immune';
                                else if (mult === 0.25) cls = 'dmg-quarter';
                                else if (mult === 0.5) cls = 'dmg-half';
                                else if (mult === 2) cls = 'dmg-2x';
                                else if (mult === 4) cls = 'dmg-4x';
                                return `<div class="effect-damage-cell"><span class="effect-damage-value ${cls}" title="${oppName}">${mult === 0 ? '0x' : mult+'×'}</span></div>`;
                            }).join('')}
                        </div>`;
                    }).join('')}
                </div>
            `;

            row.innerHTML = avatarHtml + movesHtml + damageHtml;
        }

        myRows.appendChild(row);
    }

    // 对方侧：表头（我方6只宝可梦头像）
    const oppHeader = document.createElement('div');
    oppHeader.className = 'effect-header';
    oppHeader.innerHTML = `
        <div class="effect-damage-list effect-damage-header">
            ${myTeam.map((myPokemon, idx) => {
                if (!myPokemon) return '<div class="effect-damage-item-header"></div>';
                const spritePath = myPokemon.sprite ? myPokemon.sprite.replace(/^sprites\//, '') : '';
                const pokemonName = myPokemon.name_zh || myPokemon.name || '?';
                return `<div class="effect-damage-item-header" title="${pokemonName}">
                    <img src="/sprites/${spritePath}" alt="${pokemonName}">
                    <span>${pokemonName}</span>
                </div>`;
            }).join('')}
        </div>
        <div class="effect-moves-placeholder"></div>
        <div class="effect-avatar-placeholder"></div>
    `;
    oppRows.appendChild(oppHeader);

    // 渲染对方6行
    for (let i = 0; i < 6; i++) {
        const oppPokemon = oppTeam[i];
        const row = document.createElement('div');
        row.className = 'effect-row';

        if (!oppPokemon) {
            row.innerHTML = `<div class="effect-row-empty">对方 ${i+1}</div>`;
        } else {
            const spritePath = oppPokemon.sprite ? oppPokemon.sprite.replace(/^sprites\//, '') : '';
            const pokemonName = oppPokemon.name_zh || oppPokemon.name || '?';

            // 左侧伤害列表(对我方6只宝可梦) - 每个技能一行
            const damageHtml = `
                <div class="effect-damage-grid">
                    ${(oppPokemon.moves || []).map(m => {
                        const moveType = (m.type || '').toLowerCase();
                        const power = m.power;
                        const moveName = m.name_zh || m.name || '';
                        return `<div class="effect-damage-row" title="${moveName}">
                            ${myTeam.map(myPokemon => {
                                if (!myPokemon) return '<div class="effect-damage-cell">-</div>';
                                if (power === 0 || power === null) return '<div class="effect-damage-cell"><span class="effect-damage-placeholder"></span></div>';
                                const myName = myPokemon.name_zh || myPokemon.name || '?';
                                const effectiveness = myPokemon.type_effectiveness || {};
                                const mult = effectiveness[moveType] !== undefined ? effectiveness[moveType] : 1;
                                let cls = 'dmg-normal';
                                if (mult === 0) cls = 'dmg-immune';
                                else if (mult === 0.25) cls = 'dmg-quarter';
                                else if (mult === 0.5) cls = 'dmg-half';
                                else if (mult === 2) cls = 'dmg-2x';
                                else if (mult === 4) cls = 'dmg-4x';
                                return `<div class="effect-damage-cell"><span class="effect-damage-value ${cls}" title="${myName}">${mult === 0 ? '无' : mult+'×'}</span></div>`;
                            }).join('')}
                        </div>`;
                    }).join('')}
                </div>
            `;

            // 中间技能列表
            const movesHtml = `
                <div class="effect-moves">
                    ${(oppPokemon.moves || []).map(m => {
                        const moveName = m.name_zh || m.name || '';
                        const moveType = m.type || '';
                        const typeId = TYPE_ID_MAP[moveType] || 1;
                        const power = m.power !== null ? m.power : '-';
                        const accuracy = m.accuracy !== null ? m.accuracy : '-';
                        return `<div class="effect-move-chip type-${moveType.toLowerCase()}" title="${moveType}">
                            <span class="move-name">${moveName}</span>
                            <div class="type-icon-mini" style="background-image: url('/sprites/sprites/types/generation-ix/scarlet-violet/small/${typeId}.png')"></div>
                            <span class="move-stats-mini">${power}/${accuracy}</span>
                        </div>`;
                    }).join('') || '<div class="effect-move-empty">无技能</div>'}
                </div>
            `;

            // 右侧头像
            const avatarHtml = `
                <div class="effect-avatar">
                    ${spritePath ? `<img src="/sprites/${spritePath}" alt="${pokemonName}">` : ''}
                    <div class="effect-pokemon-name">${pokemonName}</div>
                </div>
            `;

            row.innerHTML = damageHtml + movesHtml + avatarHtml;
        }

        oppRows.appendChild(row);
    }

    overlay.classList.add('open');
}

function closeTypeEffect(){
    const overlay = document.getElementById('type-effect-overlay');
    overlay.classList.remove('open');
}
