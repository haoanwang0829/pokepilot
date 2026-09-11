// ===================== 我方宝可梦切换选择器（teamAnalysis 页） =====================
// 点击我方卡片头像/名字打开搜索面板，从 champions_roster（过签宝可梦）中挑选，
// 替换当前槽位为所选宝可梦的默认配置，并刷新卡片 + 表头 + 伤害表。

let myRoster = null;        // /api/data/roster-list 返回的全部过签宝可梦
let myRosterLoaded = false;
let myRosterLoading = null; // 防并发
let pickerSlot = -1;         // 当前选择器对应的我方槽位
let pickerFilter = '';

// 打开选择器（懒加载 roster 列表）
async function openMyPicker(i, ev) {
    pickerSlot = i;
    const mon = myTeam && myTeam[i];
    const title = document.querySelector('#my-picker-overlay .picker-head h3');
    if (title) title.textContent = '选择宝可梦' + (mon ? '（替换：' + (mon.name_zh || mon.name) + '）' : '');
    document.getElementById('my-picker-search').value = '';
    pickerFilter = '';
    renderMyPickerList();
    // 懒加载一次
    if (!myRosterLoaded && !myRosterLoading) {
        myRosterLoading = loadMyRoster();
        try { await myRosterLoading; } catch (e) { /* 已在 loadMyRoster 提示 */ }
        myRosterLoading = null;
    }
    if (myRosterLoaded) renderMyPickerList();
    const overlay = document.getElementById('my-picker-overlay');
    overlay.classList.add('show');
    setTimeout(()=>{ const si=document.getElementById('my-picker-search'); if (si) si.focus(); }, 30);
}

async function loadMyRoster() {
    myRoster = [];
    try {
        const q = `season=${encodeURIComponent(currentSeason)}&format=${encodeURIComponent(currentFormat)}`;
        const res = await fetch(`/api/data/roster-list?${q}`);
        const data = await res.json();
        if (!data.success) throw new Error(data.error || '加载失败');
        myRoster = data.pokemon || [];
        myRosterLoaded = true;
        renderMyPickerList();
    } catch (e) {
        document.getElementById('my-picker-body').innerHTML = `<div class="picker-empty">候选列表加载失败：${esc(e.message)}</div>`;
    }
}

function closeMyPicker() {
    document.getElementById('my-picker-overlay').classList.remove('show');
    pickerSlot = -1;
    pickerFilter = '';
}

// 清空当前选择器对应的我方槽位（移除该宝可梦，卡片回到“槽位 N”空态）
function clearMyPokemonFromPicker() {
    const i = pickerSlot;
    if (i < 0 || !(myTeam && myTeam[i])) return;
    myTeam[i] = null;
    pokeCacheDeleteAll();
    closeMyPicker();
    renderMyCards();
    updateTableHeader();
    recomputeAllRows();
}

function onMyPickerFilter() {
    pickerFilter = (document.getElementById('my-picker-search').value || '').trim().toLowerCase();
    renderMyPickerList();
}

function renderMyPickerList() {
    const body = document.getElementById('my-picker-body');
    if (!myRosterLoaded) { body.innerHTML = '<div class="picker-empty">加载中…</div>'; return; }
    // 只列可独立构建的条目：过滤 mega 形态（mega 通过卡片上的形态切换选择）
    let list = myRoster.filter(p => !String(p.form || '').startsWith('mega'));
    if (pickerFilter) {
        list = list.filter(p => {
            const zh = (p.name_zh || '').toLowerCase();
            const slug = (p.slug || '').toLowerCase();
            const baseName = slug.replace(/-.*$/, '');
            return zh.includes(pickerFilter) || slug.includes(pickerFilter) || baseName.includes(pickerFilter);
        });
    }
    if (!list.length) { body.innerHTML = '<div class="picker-empty">未找到匹配的宝可梦</div>'; return; }
    body.innerHTML = list.map(p => {
        const sp = spritePath(p.sprite);
        return `<div class="picker-item" onclick="selectMyPokemon('${esc(p.slug)}')" title="${esc(p.name_zh || p.slug)}">
            ${sp ? `<img class="pi-sprite" src="/sprites/${esc(sp)}" alt="">` : '<div class="pi-sprite"></div>'}
            <div class="pi-name">${esc(p.name_zh || p.slug)}</div>
            ${p.has_usage ? '' : '<div class="pi-usage">无使用率</div>'}
        </div>`;
    }).join('');
}

function selectMyPokemon(slug) {
    const p = (myRoster || []).find(x => x.slug === slug);
    if (!p || pickerSlot < 0) return;
    if (!myTeam[pickerSlot]) return;
    // 若已选同一只则不再重建（避免覆盖用户的编辑）
    if (myTeam[pickerSlot].slug === p.slug && !myTeam[pickerSlot]._evoIdx) {
        closeMyPicker();
        return;
    }
    const mon = buildMyMonFromRoster(p);
    if (!mon) { alert('构建失败：缺少数据'); return; }
    // 切换宝可梦时，nickname 直接用 name 赋值（不再沿用旧宝可梦的昵称）
    mon.nickname = mon.name;
    myTeam[pickerSlot] = mon;
    pokeCacheDeleteAll();
    closeMyPicker();
    renderMyCards();
    updateTableHeader();
    recomputeAllRows();
}

// 把 roster 条目转成我方 mon（to_dict 形状），默认使用率 top1 配置
function buildMyMonFromRoster(p) {
    const natureObj = (p.natures && p.natures[0]) || null;
    const natureName = natureObj && natureObj.name ? natureObj.name : 'Serious';
    const abiObj = (p.abilities && p.abilities[0]) || null;
    const itemObj = (p.items && p.items[0]) || null;
    const evObj = (p.evs && p.evs[0]) || {};

    const evs = {
        hp: evObj.hp || 0, attack: evObj.atk || 0, defense: evObj.def || 0,
        sp_atk: evObj.spA || 0, sp_def: evObj.spD || 0, speed: evObj.spe || 0,
    };
    const base = p.base_stats || {};
    const stats = computeExactStats(base, evs, natureName);

    const damaging = (p.moves || []).filter(m => m.damaging);
    const moves = damaging.slice(0, 4).map(m => ({
        name: m.name, name_zh: m.name_zh || m.name,
        power: m.power, category: m.category, type: m.type, priority: m.priority,
    }));

    // 多形态（跳过基础形态）→ 我方 evoforms 形状
    const evoforms = (p.forms || []).filter(f => f.slug !== p.slug && (f.form || '').length).map(f => {
        const fbase = f.base_stats || base;
        // ability 恒为数组（与 mon.ability 形状一致），空则不提供
        const fabi = (f.abilities && f.abilities[0]) ? [{ name: f.abilities[0].name, name_zh: f.abilities[0].name_zh }] : [];
        return {
            slug_name: f.slug,
            form_name: f.form,
            form_name_zh: f.name_zh || f.form || '',
            base_stats: fbase,
            stats: computeExactStats(fbase, evs, natureName),
            ability: fabi,
            types: f.types || p.types || [],
            type_effectiveness: [],
            sprite: f.sprite || '',
        };
    });

    return {
        nickname: '',
        name: p.name_zh || p.slug,
        name_zh: p.name_zh || p.slug,
        slug: p.slug,
        index: 0,
        types: p.types || [],
        base_stats: base,
        stats: stats,
        evs: evs,
        nature: natureName,
        nature_en: natureName ? [{ name: natureName }] : [],
        evList: [],
        type_effectiveness: [],
        ability: abiObj ? [{ name: abiObj.name, name_zh: abiObj.name_zh || abiObj.name }] : [],
        held_item: itemObj ? [{ name: itemObj.name, name_zh: itemObj.name_zh || itemObj.name }] : [],
        moves: moves,
        formSlug: p.slug,
        sprite: p.sprite || '',
        evoforms: evoforms,
    };
}

document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeMyPicker();
});
