// ===== 查看伤害克制关系=====
function viewTypeEffectiveness(){
    const overlay = document.getElementById('type-effect-overlay');
    const myHeader = document.getElementById('my-effect-header');
    const myContent = document.getElementById('my-effect-content');
    const oppHeader = document.getElementById('opp-effect-header');
    const oppContent = document.getElementById('opp-effect-content');

    // 清空旧内容
    myHeader.innerHTML = '';
    myContent.innerHTML = '';
    oppHeader.innerHTML = '';
    oppContent.innerHTML = '';

    const myTeam = currentTeams['my-team'] || [];
    const oppTeam = currentTeams['opp-team'] || [];
    // ===== 我方侧：表头（对方6只宝可梦头像）=====
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

    // ===== 对方侧：表头（我方6只宝可梦头像）=====
    oppHeader.innerHTML = `
        <div class="effect-damage-header">
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

    // ===== 我方侧：内容（我方6只宝可梦伤害行）=====
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
                        const category = m.category;
                        const moveName = m.name_zh || m.name || '';
                        return `<div class="effect-damage-row" title="${moveName}">
                            ${oppTeam.map(oppPokemon => {
                                if (!oppPokemon) return '<div class="effect-damage-cell">-</div>';
                                if (category === 'status') return '<div class="effect-damage-cell"><span class="effect-damage-placeholder"></span></div>';
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

        myContent.appendChild(row);
    }

    // ===== 对方侧：内容（对方6只宝可梦伤害行）=====
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
                        const category = m.category;
                        const moveName = m.name_zh || m.name || '';
                        return `<div class="effect-damage-row" title="${moveName}">
                            ${myTeam.map(myPokemon => {
                                if (!myPokemon) return '<div class="effect-damage-cell">-</div>';
                                if (category === 'status') return '<div class="effect-damage-cell"><span class="effect-damage-placeholder"></span></div>';
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

        oppContent.appendChild(row);
    }

    overlay.classList.add('open');
    showDamageInfo();
}

function closeTypeEffect(){
    const overlay = document.getElementById('type-effect-overlay');
    overlay.classList.remove('open');
}
let myTeamDamages = [];
let oppTeamDamages = [];

function calcTeamDamage(myTeam, oppTeam) {
    myTeamDamages = [];
    oppTeamDamages = [];
    // 按速度降序排序
    myTeam.sort((a, b) => (b.stats?.speed || 0) - (a.stats?.speed || 0));
    oppTeam.sort((a, b) => (b.stats?.speed || 0) - (a.stats?.speed || 0));
    
    // console.log(myTeam,oppTeam);
    // 计算我方每只宝可梦对对方全队的伤害
    for (const attacker of myTeam) {
        if (!attacker) continue;
        // attacker.damageResults = [];        
        const damages = [];
        for (const defender of oppTeam) {
            if (!defender) {continue;}
            //对每个pokemon只保留伤害最高的一个+一个先制技能
            const maxDamage = {
                atkIndex:0,
                defIndex:0,
                moveName:'',
                priority:0,
                min: 0,
                max: 0,
                pctLow: 0,
                pctHigh: 0,
                effectiveness: 1,
            };
            const pdamage = {...maxDamage}
            for (const move of (attacker.moves || [])) {
                if (!move || move.category=='status' ) {
                    // attacker.damageResults.push(null);
                    continue;
                }
                const res = calcDamage(attacker, defender, move);
                if (res) {
                    const [min, max] = res.range();
                    //默认没加HP
                    const hp = (defender.stats?.hp[0] || 1) + (defender.evs?.hp || 0);
                    if (max > maxDamage.max) {
                        maxDamage.atkIndex=attacker.index,
                        maxDamage.defIndex=defender.index,
                        maxDamage.moveName=move.name_zh,
                        maxDamage.priority=move.priority,
                        maxDamage.min = min;
                        maxDamage.max = max;
                        maxDamage.pctLow = +(min / hp * 100).toFixed(1);
                        maxDamage.pctHigh = +(max / hp * 100).toFixed(1);
                        maxDamage.effectiveness = res.effectiveness || 1;
                    }  
                    if(move.priority>0){
                        pdamage.atkIndex=attacker.index,
                        pdamage.defIndex=defender.index,
                        pdamage.moveName=move.name_zh,
                        pdamage.priority=move.priority,
                        pdamage.min = min;
                        pdamage.max = max;
                        pdamage.pctLow = +(min / hp * 100).toFixed(1);
                        pdamage.pctHigh = +(max / hp * 100).toFixed(1);
                        pdamage.effectiveness = res.effectiveness || 1;

                        damages.push(pdamage);
                    }                   
                } else {
                    // damages.push(null);
                }
            }
            if (maxDamage.max > 0 && maxDamage.priority<=0){damages.push(maxDamage)};          
        }
        if (Array.isArray(damages) && damages.length > 0) {
            myTeamDamages.push(...damages);
        }
    }

    // 计算对方每只宝可梦对我方全队的伤害
    for (const attacker of oppTeam) {
        if (!attacker) continue;
        // attacker.damageResults = [];
       
        const damages = [];
        for (const defender of myTeam) {
            if (!defender) {continue;}
            //对每个pokemon只保留伤害最高的一个+一个先制技能
            const maxDamage = {
                atkIndex:0,
                defIndex:0,
                moveName:'',
                priority:0,
                min: 0,
                max: 0,
                pctLow: 0,
                pctHigh: 0,
                effectiveness: 1,
            };
            const pdamage = {...maxDamage}
            for (const move of (attacker.moves || [])) {
                if (!move || move.category=='status') {
                    continue;
                }
                const res = calcDamage(attacker, defender, move);
                if (res) {
                    const [min, max] = res.range();
                    const hp = (defender.stats?.hp || 1) + (defender.evs?.hp || 0);
                    if (max > maxDamage.max) {
                        maxDamage.atkIndex=attacker.index,
                        maxDamage.defIndex=defender.index,
                        maxDamage.moveName=move.name_zh,
                        maxDamage.priority=move.priority,
                        maxDamage.min = min;
                        maxDamage.max = max;
                        maxDamage.pctLow = +(min / hp * 100).toFixed(1);
                        maxDamage.pctHigh = +(max / hp * 100).toFixed(1);
                        maxDamage.effectiveness = res.effectiveness || 1;
                    }
                    if(move.priority>0){
                        pdamage.atkIndex=attacker.index,
                        pdamage.defIndex=defender.index,
                        pdamage.moveName=move.name_zh,
                        pdamage.priority=move.priority,
                        pdamage.min = min;
                        pdamage.max = max;
                        pdamage.pctLow = +(min / hp * 100).toFixed(1);
                        pdamage.pctHigh = +(max / hp * 100).toFixed(1);
                        pdamage.effectiveness = res.effectiveness || 1;

                        damages.push(pdamage);
                    }  
                } else {
                    // damages.push(null);
                }
            }
            if (maxDamage.max > 0 && maxDamage.priority<=0){damages.push(maxDamage)};            
        }
        if (Array.isArray(damages) && damages.length > 0) {
            oppTeamDamages.push(...damages);
        }
    }
    // console.log(myTeamDamages,oppTeamDamages);
}
// ======================
// 外部定义：宝可梦名称映射工具（全局复用）
// ======================
function mapName(slug) {
  // 你的 slug => smogon 英文名称 映射表
  const nameMap = {
    'basculegion-male': 'basculegion',    
    'basculegion-female': 'basculegion-F',
    'floette-eternal-flower':'Floette-Eternal',
    // 在这里继续加你需要的映射...
  };

  // 有映射返回映射，没有返回原 slug（自动小写兼容）
  return nameMap[slug?.toLowerCase()] || slug;
}
function calcDamage(attacker, defender, move){
    try {
        const gen = window.calc.Generations.get(9);
        const { calculate, Pokemon, Move } = window.calc;

        const atkPokemon = new Pokemon(gen, mapName(attacker.slug), {
            level: 50,
            ivs: { hp:31, atk:31, def:31, spa:31, spd:31, spe:31 },
            evs: {
                hp: attacker.evs?.hp*8-4 || 0,
                atk: attacker.evs?.attack *8-4|| 0,
                def: attacker.evs?.defense*8-4 || 0,
                spa: attacker.evs?.sp_atk*8-4 || 0,
                spd: attacker.evs?.sp_def*8-4 || 0,
                spe: attacker.evs?.speed*8-4 || 0,
            },
            nature: (attacker.nature_en && attacker.nature_en[0]?.name) || attacker.nature || 'Hardy',
            ability:attacker.ability[0].name,
        });

        const defPokemon = new Pokemon(gen, mapName(defender.slug), {
            level: 50,
            ivs: { hp:31, atk:31, def:31, spa:31, spd:31, spe:31 },
            evs: {
                hp: defender.evs?.hp*8-4 || 0,
                atk: defender.evs?.attack*8-4 || 0,
                def: defender.evs?.defense*8-4 || 0,
                spa: defender.evs?.sp_atk*8-4 || 0,
                spd: defender.evs?.sp_def*8-4 || 0,
                spe: defender.evs?.speed*8-4 || 0,
            },
            nature: (defender.nature_en && defender.nature_en[0]?.name) || defender.nature || 'Hardy',
            ability:defender.ability[0].name,
        });

        const calcMove = new Move(gen, move.name);
        const res = calculate(gen, atkPokemon, defPokemon, calcMove);
        return res;
    } catch (e) {
        console.log('calcDamage error:', e,attacker,defender,move);
    }
    return null;
}

const selectedMyIndices = {};
const selectedOppIndices = {};

function showDamageInfo(){
    document.getElementById('damage-info').style.display = 'block';
    const myTeam = [...(currentTeams['my-team'] || [])];
    const oppTeam = [...(currentTeams['opp-team'] || [])];
    calcTeamDamage(myTeam,oppTeam);

    const header = document.querySelector('.damage-info-header');
    const myAvatars = myTeam.map((p, i) => {
        if (!p) return null;
        const path = p.sprite ? p.sprite.replace(/^sprites\//, '') : '';
        const name = p.name_zh || p.name || '?';
        const sel = selectedMyIndices[p.index] ? ' selected' : '';
        return `<div class="di-avatar${sel}" data-team="my" data-index="${p.index}" onclick="selectedPokemon(this)" title="${name}">
            ${path ? `<img src="/sprites/${path}" alt="${name}">` : ''}
        </div>`;
    }).filter(Boolean).join('');

    const oppAvatars = oppTeam.map((p, i) => {
        if (!p) return null;
        const path = p.sprite ? p.sprite.replace(/^sprites\//, '') : '';
        const name = p.name_zh || p.name || '?';
        const sel = selectedOppIndices[p.index] ? ' selected' : '';
        return `<div class="di-avatar${sel}" data-team="opp" data-index="${p.index}" onclick="selectedPokemon(this)" title="${name}">
            ${path ? `<img src="/sprites/${path}" alt="${name}">` : ''}
        </div>`;
    }).filter(Boolean).join('');

    header.innerHTML = `
        <div class="di-avatar-group di-my-side">${myAvatars}</div>
        <div class="di-divider"></div>
        <div class="di-avatar-group di-opp-side">${oppAvatars}</div>
    `;
}

function selectedPokemon(el){
    const team = el.dataset.team;
    const idx = parseInt(el.dataset.index);
    const map = team === 'my' ? selectedMyIndices : selectedOppIndices;
    if (map[idx]) {
        delete map[idx];
        el.classList.remove('selected');
    } else {
        map[idx] = true;
        el.classList.add('selected');
    }
    //根据选中的数据，展示伤害信息
    showDamageInfoDetail();
}
function showDamageInfoDetail() {
    const myTeam = currentTeams['my-team'] || [];
    const oppTeam = currentTeams['opp-team'] || [];
    const myIdxList = Object.keys(selectedMyIndices).map(Number);
    const oppIdxList = Object.keys(selectedOppIndices).map(Number);
    const myPanel = document.getElementById('di-my-damage');
    const oppPanel = document.getElementById('di-opp-damage');

    if (myIdxList.length === 0 || oppIdxList.length === 0) {
        myPanel.innerHTML = '<div class="di-detail-empty"></div>';
        oppPanel.innerHTML = '<div class="di-detail-empty"></div>';
        return;
    }

    // 生成带攻击方合并单元格的表格
    const generateDamageTable = (damageList, isMyTeam) => {
        const rows = [];
        const atkTeam = isMyTeam ? myTeam : oppTeam;
        const defTeam = isMyTeam ? oppTeam : myTeam;

        // 1. 先筛选出符合条件的伤害数据
        for (const d of damageList) {
            const atkMatch = isMyTeam
                ? myIdxList.includes(d.atkIndex) && oppIdxList.includes(d.defIndex)
                : oppIdxList.includes(d.atkIndex) && myIdxList.includes(d.defIndex);
            if (!atkMatch) continue;

            const atk = atkTeam.find(p => p.index === d.atkIndex);
            const def = defTeam.find(p => p.index === d.defIndex);
            const atkName = atk?.name_zh || atk?.name || '?';
            const defName = def?.name_zh || def?.name || '?';
            const moveName = d.priority > 0 ? `+${d.priority} ${d.moveName}` : d.moveName;
            const damageInfo = `${d.pctLow}%~${d.pctHigh}% (${d.min}-${d.max})`;

            rows.push({ atkName, defName, moveName, damageInfo });
        }

        if (rows.length === 0) {
            return `
                <table class="di-detail-table">
                    <thead><tr><th colspan="4"></th></tr></thead>
                </table>
            `;
        }

        // 2. 计算攻击方跨行合并（核心逻辑）
        const renderRows = [];
        let i = 0;
        while (i < rows.length) {
            const currentAtk = rows[i].atkName;
            let span = 1;

            // 统计连续相同攻击方的数量
            while (i + span < rows.length && rows[i + span].atkName === currentAtk) {
                span++;
            }

            // 第一条：添加 rowspan，其余不渲染攻击方
            for (let j = 0; j < span; j++) {
                const item = rows[i + j];
                if (j === 0) {
                    renderRows.push(`
                        <tr class="di-detail-row">
                            <td class="atk-merge" rowspan="${span}">${item.atkName}</td>
                            <td>${item.defName}</td>
                            <td>${item.moveName}</td>
                            <td class="di-damage-info">${item.damageInfo}</td>
                        </tr>
                    `);
                } else {
                    renderRows.push(`
                        <tr class="di-detail-row">
                            <td>${item.defName}</td>
                            <td>${item.moveName}</td>
                            <td class="di-damage-info">${item.damageInfo}</td>
                        </tr>
                    `);
                }
            }

            i += span;
        }

        return `
            <table class="di-detail-table">
                <tbody>${renderRows.join('')}</tbody>
            </table>
        `;
    };

    myPanel.innerHTML = generateDamageTable(myTeamDamages, true);
    oppPanel.innerHTML = generateDamageTable(oppTeamDamages, false);
}

function showDamageInfoDetail2(){
    const myTeam = currentTeams['my-team'] || [];
    const oppTeam = currentTeams['opp-team'] || [];
    const myIdxList = Object.keys(selectedMyIndices).map(Number);
    const oppIdxList = Object.keys(selectedOppIndices).map(Number);
    const myPanel = document.getElementById('di-my-damage');
    const oppPanel = document.getElementById('di-opp-damage');

    if (myIdxList.length === 0 || oppIdxList.length === 0) {
        myPanel.innerHTML = '<div class="di-detail-empty"></div>';
        oppPanel.innerHTML = '<div class="di-detail-empty"></div>';
        return;
    }

    let myRows = '';
    for (const d of myTeamDamages) {
        if (!myIdxList.includes(d.atkIndex) || !oppIdxList.includes(d.defIndex)) continue;
        const atk = myTeam.find(p => p.index === d.atkIndex);
        const def = oppTeam.find(p => p.index === d.defIndex);
        const an = atk?.name_zh || atk?.name || '?';
        const dn = def?.name_zh || def?.name || '?';
        const moveText = d.priority > 0 ? `+${d.priority} ${d.moveName}` : d.moveName;

        myRows += `<div class="di-detail-row">${an} → ${dn} ${moveText}: ${d.pctLow}%~${d.pctHigh}% (${d.min}-${d.max})</div>`;
    }
    myPanel.innerHTML = myRows || '<div class="di-detail-empty"></div>';

    let oppRows = '';
    for (const d of oppTeamDamages) {
        if (!oppIdxList.includes(d.atkIndex) || !myIdxList.includes(d.defIndex)) continue;
        const atk = oppTeam.find(p => p.index === d.atkIndex);
        const def = myTeam.find(p => p.index === d.defIndex);
        const an = atk?.name_zh || atk?.name || '?';
        const dn = def?.name_zh || def?.name || '?';

        const moveText = d.priority > 0 ? `+${d.priority} ${d.moveName}` : d.moveName;

        oppRows += `<div class="di-detail-row">${an} → ${dn} ${moveText}: ${d.pctLow}%~${d.pctHigh}% (${d.min}-${d.max})</div>`;
    }
    oppPanel.innerHTML = oppRows || '<div class="di-detail-empty"></div>';
}