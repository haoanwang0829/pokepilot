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
                    if (max > maxDamage.max && move.priority<=0) {
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
                        const pdamage = {
                            atkIndex:attacker.index,
                            defIndex:defender.index,
                            moveName:move.name_zh,
                            priority:move.priority,
                            min,
                            max,
                            pctLow: +(min / hp * 100).toFixed(1),
                            pctHigh: +(max / hp * 100).toFixed(1),
                            effectiveness: res.effectiveness || 1,
                        };

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
                // console.log(attacker.name_zh,defender.name_zh,move.name_zh,res);
                if (res) {
                    const [min, max] = res.range();
                    const hp = (defender.stats?.hp || 1) + (defender.evs?.hp || 0);
                    if (max > maxDamage.max && move.priority<=0) {
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
                        // 每次先制都新建全新对象，不再复用引用
                        const pdamage = {
                            atkIndex:attacker.index,
                            defIndex:defender.index,
                            moveName:move.name_zh,
                            priority:move.priority,
                            min,
                            max,
                            pctLow: +(min / hp * 100).toFixed(1),
                            pctHigh: +(max / hp * 100).toFixed(1),
                            effectiveness: res.effectiveness || 1,
                        };
                        damages.push(pdamage);
                        // console.log(pdamage,damages);
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
    "aegislash":"Aegislash-Shield",
    "aegislash-blade-forme":"Aegislash-Blade",
    // 在这里继续加你需要的映射...
  };

  // 有映射返回映射，没有返回原 slug（自动小写兼容）
  return nameMap[slug?.toLowerCase()] || slug;
}
// 1. 全局 Mega 石列表（全部小写，匹配时统一转小写对比）
const MEGA_STONES = [
  "gengarite","gardevoirite","ampharosite","venusaurite","charizardite x","blastoisinite","mewtwonite x","mewtwonite y","blazikenite","medichamite","houndoominite","aggronite","banettite","tyranitarite","scizorite","pinsirite","aerodactylite","lucarionite","abomasite","kangaskhanite","gyaradosite","absolite","charizardite y","alakazite","heracronite","mawilite","manectite","garchompite","latiasite","latiosite","swampertite","sceptilite","sablenite","altarianite","galladite","audinite","metagrossite","sharpedonite","slowbronite","steelixite","pidgeotite","glalitite","diancite","cameruptite","lopunnite","salamencite","beedrillite","clefablite","victreebelite","starminite","dragoninite","meganiumite","feraligite","skarmorite","froslassite","heatranite","darkranite","emboarite","excadrite","scolipite","scraftinite","eelektrossite","chandelurite","chesnaughtite","delphoxite","greninjite","pyroarite","floettite","malamarite","barbaracite","dragalgite","hawluchanite","zygardite","drampanite","zeraorite","falinksite","raichunite x","raichunite y","chimechite","absolite z","staraptite","staraptornite","garchompite z","lucarionite z","golurkite","meowsticite","crabominite","golisopite","magearnite","scovillainite","baxcalibrite","tatsugirinite"
  ,"drampite","starmiite","dragonitite","feraligatrite","hawluchite","greninjaite","skarmoryite"
  // 在这里追加你所有用到的mega石小写名称
];

function calcDamage(attacker, defender, move){
    try {
        const gen = window.calc.Generations.get(9);
        const { calculate, Pokemon, Move,Field } = window.calc;
        // ====== 处理攻击者道具：是mega石则丢弃item字段 ======
            let atkItemOpt;
            if (attacker.item) {
            const itemLower = attacker.item.toLowerCase();
            // 不在mega石列表才赋值，mega石不传入item
            if (!MEGA_STONES.includes(itemLower)) {
                atkItemOpt = attacker.item;
            }
            }
        const atkPokemon = new Pokemon(gen, mapName(attacker.slug), {
            level: 50,
            ivs: { hp:31, atk:31, def:31, spa:31, spd:31, spe:31 },
            evs: {
                hp: attacker.evs?.hp > 0 ? attacker.evs.hp * 8 - 4 : 0,
                atk: attacker.evs?.attack > 0 ? attacker.evs.attack * 8 - 4 : 0,
                def: attacker.evs?.defense > 0 ? attacker.evs.defense * 8 - 4 : 0,
                spa: attacker.evs?.sp_atk > 0 ? attacker.evs.sp_atk * 8 - 4 : 0,
                spd: attacker.evs?.sp_def > 0 ? attacker.evs.sp_def * 8 - 4 : 0,
                spe: attacker.evs?.speed > 0 ? attacker.evs.speed * 8 - 4 : 0,
            },
            nature: (attacker.nature_en && attacker.nature_en[0]?.name) || attacker.nature || 'Hardy',
            ability:attacker.ability[0].name,
             // 只有非mega石才会存在，mega石该字段直接不写
            ...(atkItemOpt ? { item: atkItemOpt } : {}),
        });
        // ====== 处理防御者道具，逻辑完全一致 ======
            let defItemOpt;
            if (defender.item) {
            const itemLower = defender.item.toLowerCase();
            if (!MEGA_STONES.includes(itemLower)) {
                defItemOpt = defender.item;
            }
            }
        const defPokemon = new Pokemon(gen, mapName(defender.slug), {
            level: 50,
            ivs: { hp:31, atk:31, def:31, spa:31, spd:31, spe:31 },
            evs: {
                hp: defender.evs?.hp > 0 ? defender.evs.hp * 8 - 4 : 0,
                atk: defender.evs?.attack > 0 ? defender.evs.attack * 8 - 4 : 0,
                def: defender.evs?.defense > 0 ? defender.evs.defense * 8 - 4 : 0,
                spa: defender.evs?.sp_atk > 0 ? defender.evs.sp_atk * 8 - 4 : 0,
                spd: defender.evs?.sp_def > 0 ? defender.evs.sp_def * 8 - 4 : 0,
                spe: defender.evs?.speed > 0 ? defender.evs.speed * 8 - 4 : 0,
            },
            nature: (defender.nature_en && defender.nature_en[0]?.name) || defender.nature || 'Hardy',
            ability:defender.ability[0].name,
            ...(defItemOpt ? { item: defItemOpt } : {}),
            ignoreItemErrors: true, // 核心：关闭道具匹配校验，消除megaStone报错
        });

        const calcMove = new Move(gen, move.name);
        // ==========构建Field战场对象【核心新增】==========
        const field = new Field(gen);
        // 1. 天气 weather: 'Sun'|'Rain'|'Sand'|'Hail'|'HarshSun'|'HeavyRain'|'StrongWinds'|undefined
        // if(fieldConfig.weather) field.weather = fieldConfig.weather;
        // 2. 四大场地 terrain: 'Electric'|'Grassy'|'Misty'|'Psychic'|undefined
        // if(fieldConfig.terrain) field.terrain = fieldConfig.terrain;
        // 3. 对战模式：单打/双打 isDoubles(双打技能威力修正)
        field.isDoubles = battleMode === 'double' || battleMode === 'doubles' || battleMode === 2;

        // 4. 墙壁：反射壁Reflect、光墙Light Screen
        // if(fieldConfig.screens) {
        //     if(fieldConfig.screens.reflect) field.reflect = fieldConfig.screens.reflect; // true=存在反射壁
        //     if(fieldConfig.screens.lightScreen) field.lightScreen = fieldConfig.screens.lightScreen; // true=光墙
        // }

        // 5. 场地钉子：隐形岩、钉子、毒钉、黏黏网
        // if(fieldConfig.hazards) {
        //     // 我方场地钉子
        //     field.attackerSide.stealthRock = !!fieldConfig.hazards.atkStealthRock; // 隐形岩
        //     field.attackerSide.spikes = fieldConfig.hazards.atkSpikes ?? 0; // 钉子层数0~3
        //     field.attackerSide.toxicSpikes = fieldConfig.hazards.atkToxicSpikes ?? 0; //毒钉0~2
        //     field.attackerSide.stickyWeb = !!fieldConfig.hazards.atkStickyWeb; //黏黏网
        //     // 防守方场地钉子
        //     field.defenderSide.stealthRock = !!fieldConfig.hazards.defStealthRock;
        //     field.defenderSide.spikes = fieldConfig.hazards.defSpikes ?? 0;
        //     field.defenderSide.toxicSpikes = fieldConfig.hazards.defToxicSpikes ?? 0;
        //     field.defenderSide.stickyWeb = !!fieldConfig.hazards.defStickyWeb;
        // }

        // 6. 灾祸（命玉四圣器：剑/玉/钵/鼎）Sword/Vessel/Bead/Tablet
        // if(fieldConfig.ruin) {
        //     field.ruinSword = !!fieldConfig.ruin.sword;
        //     field.ruinVessel = !!fieldConfig.ruin.vessel;
        //     field.ruinBeads = !!fieldConfig.ruin.bead;
        //     field.ruinTablets = !!fieldConfig.ruin.tablet;
        // }

        // 7. 其他全局：重力、戏法空间等按需扩展 field.gravity = true;

        // 第五参数传入field
        const res = calculate(gen, atkPokemon, defPokemon, calcMove, field);
        return res;
    } catch (e) {
        console.log('calcDamage error:', e,attacker,defender,move);
    }
    return null;
}

function getDamageLabel(pctLow, pctHigh) {
  if (pctLow >= 100 && pctHigh >= 100) return { label: '确一', color: '#e74c3c' };
  if (pctHigh >= 100) return { label: '乱一', color: '#e74c3c' };
  if (pctLow >= 50 && pctHigh >= 50) return { label: '确二', color: '#f0c000' };
  if (pctHigh >= 50) return { label: '乱二', color: '#f0c000' };
  return { label: '', color: '' };
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
            const baseSpd = atk?.base_stats?.speed ?? 0;
            const ev = atk?.evs?.speed ?? 0;
            const natureMult = typeof getNatureSpeedMultiplier === 'function' ? getNatureSpeedMultiplier(atk.nature_en) : 1.0;
            const speed = Math.floor((baseSpd + 20 + ev) * natureMult);
            const atkLabel = `${atkName} (速${speed})`;
            const moveName = d.priority > 0 ? `+${d.priority} ${d.moveName}` : d.moveName;
            const { label, color } = getDamageLabel(d.pctLow, d.pctHigh);
            const labelHtml = label ? `<span style="color:${color};font-weight:bold;margin-right:4px">${label}</span>` : '';
            const damageInfo = `${labelHtml}${d.pctLow}%~${d.pctHigh}% (${d.min}-${d.max})`;

            rows.push({ atkName, atkLabel, defName, moveName, damageInfo });
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
            const isLastGroup = i + span >= rows.length;
            for (let j = 0; j < span; j++) {
                const item = rows[i + j];
                const isLastInGroup = j === span - 1;
                const rowClass = isLastInGroup && !isLastGroup
                    ? 'di-detail-row atk-group-end'
                    : 'di-detail-row';
                if (j === 0) {
                    renderRows.push(`
                        <tr class="${rowClass}">
                            <td class="atk-merge" rowspan="${span}"><span class="di-text-bg">${item.atkLabel}</span></td>
                            <td><span class="di-text-bg">${item.defName}</span></td>
                            <td><span class="di-text-bg">${item.moveName}</span></td>
                            <td class="di-damage-info"><span class="di-text-bg">${item.damageInfo}</span></td>
                        </tr>
                    `);
                } else {
                    renderRows.push(`
                        <tr class="${rowClass}">
                            <td><span class="di-text-bg">${item.defName}</span></td>
                            <td><span class="di-text-bg">${item.moveName}</span></td>
                            <td class="di-damage-info"><span class="di-text-bg">${item.damageInfo}</span></td>
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