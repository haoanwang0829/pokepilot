// ===================== 我方队伍编辑保存（teamAnalysis 页） =====================
// 编辑（技能/道具/性格/特性/EV/形态）默认只改内存 myTeam。此文件将 myTeam 序列化
// 写回槽位（保存当前槽位 / 另存为新槽位），复用 POST /api/teams/save。

// 序列化单只宝可梦为后端 roster 所需的 to_dict 形状，并剔除临时编辑状态
function serializeMyMon(mon) {
    if (!mon) return null;
    const out = {};
    for (const k of ['nickname','name','name_zh','slug','index','stats','base_stats',
                     'evs','nature','nature_en','evList','type_effectiveness','sprite']) {
        if (mon[k] !== undefined) out[k] = mon[k];
    }
    // types 恒有值（宝可梦必有属性）
    if (Array.isArray(mon.types) && mon.types.length) out.types = mon.types;
    // ability / held_item：可能是字符串、对象、或列表，原样复制
    if (mon.ability !== undefined) out.ability = mon.ability;
    if (mon.held_item !== undefined) out.held_item = mon.held_item;
    if (mon.moves !== undefined) out.moves = mon.moves;
    // 多形态
    if (Array.isArray(mon.evoforms) && mon.evoforms.length) out.evoforms = mon.evoforms;
    return out;
}

function serializeMyTeam() {
    const roster = (myTeam || []).map(serializeMyMon).filter(Boolean);
    // 直传顶层 roster（后端 /api/teams/save 读取 body.roster，写成扁平格式 {trainer_name, roster}；
    // 若嵌套 team.roster 后端会落到 temp.json 旧数据，导致保存不回切换后的宝可梦）
    return JSON.parse(JSON.stringify({ roster }));
}

// 保存到当前选中槽位
async function saveMyTeam() {
    const sel = document.getElementById('team-select');
    const slotId = sel ? sel.value : null;
    if (!slotId) { alert('未选择队伍槽位'); return; }
    if (!(myTeam || []).length) { alert('我方队伍为空，无可保存内容'); return; }
    try {
        const payload = serializeMyTeam();
        payload.slot_id = slotId;
        const res = await fetch('/api/teams/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (data.success) {
            alert(`队伍已保存：${data.slot_name}`);
        } else {
            alert('保存失败：' + (data.error || '未知错误'));
        }
    } catch (e) {
        alert('保存失败：' + e.message);
    }
}

// 另存为新槽位
async function saveAsNewTeam() {
    const nameInput = document.getElementById('save-as-name');
    const name = nameInput ? nameInput.value.trim() : '';
    if (!name) { alert('请输入队伍名称'); return; }
    if (!(myTeam || []).length) { alert('我方队伍为空，无可保存内容'); return; }
    try {
        const payload = serializeMyTeam();
        payload.slot_name = name;
        const res = await fetch('/api/teams/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        closeSaveAsModal();
        if (data.success) {
            alert('新队伍已保存：' + data.slot_name);
            // 刷新下拉并切换到新槽位
            await loadTeamSlots();
            const sel = document.getElementById('team-select');
            if (sel) { sel.value = data.slot_id; await loadTeamSlot(data.slot_id); }
        } else {
            alert('保存失败：' + (data.error || '未知错误'));
        }
    } catch (e) {
        alert('保存失败：' + e.message);
    }
}

function openSaveAsModal() {
    const overlay = document.getElementById('save-as-overlay');
    const input = document.getElementById('save-as-name');
    if (input) input.value = '';
    if (overlay) overlay.style.display = 'flex';
    if (input) setTimeout(()=>input.focus(), 30);
}

function closeSaveAsModal() {
    const overlay = document.getElementById('save-as-overlay');
    if (overlay) overlay.style.display = 'none';
}

// Enter 键直接保存
document.addEventListener('keydown', (e)=>{
    if (e.key === 'Enter') {
        const overlay = document.getElementById('save-as-overlay');
        if (overlay && overlay.style.display === 'flex') saveAsNewTeam();
    }
});
