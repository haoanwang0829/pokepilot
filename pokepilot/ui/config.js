/**
 * Card Layout Configuration Loader
 * Loads configuration from card_layout.json
 * Shared with Python backend
 */

let CARD_LAYOUT_CONFIG = null;
let OPPONENT_TEAM_LAYOUT_CONFIG = null;

/**
 * Load configuration from JSON file
 * Call this before using the configuration
 */
async function loadCardLayoutConfig() {
  try {
    const response = await fetch('/api/get-layout-config');

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const result = await response.json();

    if (!result.success) {
      throw new Error(result.error || 'API returned error');
    }

    CARD_LAYOUT_CONFIG = result.data;
    updateLayoutDisplayValues();
    return CARD_LAYOUT_CONFIG;

  } catch (error) {
    const defaultConfig = getDefaultCardConfig();
    CARD_LAYOUT_CONFIG = defaultConfig;
    updateLayoutDisplayValues();
    return defaultConfig;
  }
}

/**
 * Load opponent team layout configuration from JSON file
 */
async function loadOpponentTeamLayoutConfig() {
  try {
    const response = await fetch('/config/opponent_team_layout.json');

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    OPPONENT_TEAM_LAYOUT_CONFIG = await response.json();
    return OPPONENT_TEAM_LAYOUT_CONFIG;

  } catch (error) {
    console.error('Failed to load opponent team layout config:', error);
    OPPONENT_TEAM_LAYOUT_CONFIG = getDefaultOpponentTeamConfig();
    return OPPONENT_TEAM_LAYOUT_CONFIG;
  }
}

/**
 * Get default opponent team configuration
 */
function getDefaultOpponentTeamConfig() {
  return {
    base_resolution: { width: 1920, height: 1080 },
    slot_layout: {
      x0: 1554,
      y0: 153,
      width: 300,
      height: 115,
      gap: 11,
      count: 6
    },
    slot_regions: {
      sprite: { rx0: 0.2152, ry0: 0.1466, rx1: 0.5662, ry1: 0.9914 },
      type1: { rx0: 0.6391, ry0: 0.1293, rx1: 0.7980, ry1: 0.5517 },
      type2: { rx0: 0.8146, ry0: 0.1207, rx1: 0.9735, ry1: 0.5431 }
    }
  };
}

function updateLayoutDisplayValues() {
  if (CARD_LAYOUT_CONFIG && CARD_LAYOUT_CONFIG.layout) {
    const topXElem = document.getElementById('top-x-value');
    const topYElem = document.getElementById('top-y-value');
    if (topXElem) topXElem.textContent = CARD_LAYOUT_CONFIG.layout.top_x;
    if (topYElem) topYElem.textContent = CARD_LAYOUT_CONFIG.layout.top_y;
  }
}

/**
 * Get default fallback configuration (if JSON load fails)
 */
function getDefaultCardConfig() {
  return {
    layout: {
      top_x: 190,
      top_y: 265,
      rect_w: 738,
      rect_h: 186,
      vertical_gap: 31,
      horizontal_gap: 64,
    },
    regions: {
      sprite: {
        rx: 0.01,
        ry: -0.11,
        size: 66,
        label: "Sprite",
      },
      type1: {
        rx: 0.471,
        ry: 0.05,
        size: 30,
        label: "Type1",
      },
      type2: {
        rx: 0.528,
        ry: 0.05,
        size: 30,
        label: "Type2",
      },
    },
    stat_boxes: {
      box_w: 0.189,
      box_h: 0.19,
      left_x: 0.287,
      right_x: 0.762,
      y_tops: [0.2708, 0.5200, 0.7692],
    },
    stat_arrows: [
      { name: "hp", x: 0.162, y: 0.302, size: 27 },
      { name: "attack", x: 0.182, y: 0.552, size: 27 },
      { name: "defense", x: 0.183, y: 0.79, size: 27 },
      { name: "sp_atk", x: 0.653, y: 0.302, size: 27 },
      { name: "sp_def", x: 0.656, y: 0.552, size: 27 },
      { name: "speed", x: 0.656, y: 0.79, size: 27 },
    ],
    bg_colors_multi: [[221, 237, 245], [200, 95, 115]],
  };
}

/**
 * Generate card positions from layout parameters
 */
function generateCardPositions() {
  if (!CARD_LAYOUT_CONFIG) {
    console.error('Config not loaded. Call loadCardLayoutConfig() first');
    return [];
  }

  const layout = CARD_LAYOUT_CONFIG.layout;
  const cards = {
    left_cards: [],
    right_cards: [],
  };

  // Generate left 3 cards
  for (let i = 0; i < 3; i++) {
    const y = layout.top_y + i * (layout.rect_h + layout.vertical_gap);
    cards.left_cards.push({
      slot: i + 1,
      x: layout.top_x,
      y: y,
      w: layout.rect_w,
      h: layout.rect_h,
    });
  }

  // Generate right 3 cards
  const right_x = layout.top_x + layout.rect_w + layout.horizontal_gap;
  for (let i = 0; i < 3; i++) {
    const y = layout.top_y + i * (layout.rect_h + layout.vertical_gap);
    cards.right_cards.push({
      slot: i + 4,
      x: right_x,
      y: y,
      w: layout.rect_w,
      h: layout.rect_h,
    });
  }

  return cards;
}

/**
 * Get all card positions (left + right)
 */
function getAllCardPositions() {
  const cards = generateCardPositions();
  return [...cards.left_cards, ...cards.right_cards];
}

/**
 * Generate opponent team slot positions (in pixels)
 */
function generateOpponentTeamSlots() {
  if (!OPPONENT_TEAM_LAYOUT_CONFIG) {
    console.error('Opponent team config not loaded. Call loadOpponentTeamLayoutConfig() first');
    return [];
  }

  const slotCfg = OPPONENT_TEAM_LAYOUT_CONFIG.slot_layout;
  const slots = [];

  for (let i = 0; i < slotCfg.count; i++) {
    const y = slotCfg.y0 + i * (slotCfg.height + slotCfg.gap);

    slots.push({
      slot: i + 1,
      x: slotCfg.x0,
      y: y,
      w: slotCfg.width,
      h: slotCfg.height,
    });
  }

  return slots;
}
