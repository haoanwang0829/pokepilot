/**
 * Layout Overlay - Draw card boundaries on video feed
 * Handles canvas drawing and overlay toggle
 */

// UI 颜色定义
const OVERLAY_COLORS = {
  card: "#00FF00",      // 绿色 - 卡片框
  sprite: "#FF0000",    // 红色 - sprite区域
  type1: "#00FFFF",     // 青色 - type1区域
  type2: "#FFA500",     // 橙色 - type2区域
};

const OPP_OVERLAY_COLORS = {
  slot: "#FFD700",      // 金色 - 槽框
  sprite: "#FF69B4",    // 热粉 - sprite区域
  type1: "#00FF7F",     // 春绿 - type1区域
  type2: "#FF6347",     // 番茄 - type2区域
};

class LayoutOverlay {
  constructor() {
    this.canvas = document.getElementById('layout-canvas');
    this.video = document.getElementById('video');

    if (!this.canvas || !this.video) {
      return;
    }

    this.ctx = this.canvas.getContext('2d');
    this.isVisible = false;
    this.animationFrameId = null;

    this.setupCanvas();
    this.setupVideoListeners();
  }

  setupCanvas() {
    // Update canvas size when video is loaded or resized
    if (this.video.readyState >= 2) {
      this.updateCanvasSize();
    }
  }

  setupVideoListeners() {
    // Update canvas size when video dimensions change
    this.video.addEventListener('loadedmetadata', () => this.updateCanvasSize());
    this.video.addEventListener('play', () => this.updateCanvasSize());
    this.video.addEventListener('resize', () => this.updateCanvasSize());

    // Watch for video container size changes
    const observer = new ResizeObserver(() => this.updateCanvasSize());
    const container = this.video.parentElement;
    observer.observe(container);
  }

  updateCanvasSize() {
    const container = this.video.parentElement;
    const rect = container.getBoundingClientRect();

    this.canvas.width = rect.width;
    this.canvas.height = rect.height;

    // Redraw if visible
    if (this.isVisible) {
      this.draw();
    }
  }

  getScaleFactor() {
    // Calculate scale factor between original image coordinates and canvas coordinates
    if (!this.video.videoWidth || !this.video.videoHeight) {
      return 1;
    }

    const canvasRect = this.canvas.getBoundingClientRect();
    const videoAspect = this.video.videoWidth / this.video.videoHeight;
    const canvasAspect = canvasRect.width / canvasRect.height;

    if (videoAspect > canvasAspect) {
      // Video is wider, limited by height
      return canvasRect.height / this.video.videoHeight;
    } else {
      // Canvas is wider, limited by width
      return canvasRect.width / this.video.videoWidth;
    }
  }

  getVideoOffset() {
    // Get the position of the video content within the canvas
    const canvasRect = this.canvas.getBoundingClientRect();
    const scale = this.getScaleFactor();
    const scaledWidth = this.video.videoWidth * scale;
    const scaledHeight = this.video.videoHeight * scale;

    return {
      x: (canvasRect.width - scaledWidth) / 2,
      y: (canvasRect.height - scaledHeight) / 2,
      scale: scale,
    };
  }

  draw() {
    const { x: offsetX, y: offsetY, scale } = this.getVideoOffset();

    // Clear canvas
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    if (scale <= 0) return;

    const cards = getAllCardPositions();

    // Draw card frames
    cards.forEach((card) => {
      this.drawCard(card, offsetX, offsetY, scale);
    });

    // Schedule next frame if visible
    if (this.isVisible) {
      this.animationFrameId = requestAnimationFrame(() => this.draw());
    }
  }

  drawCard(card, offsetX, offsetY, scale) {
    // Draw main card frame
    const x0 = offsetX + card.x * scale;
    const y0 = offsetY + card.y * scale;
    const w = card.w * scale;
    const h = card.h * scale;

    // Card border
    this.ctx.strokeStyle = OVERLAY_COLORS.card;
    this.ctx.lineWidth = 2;
    this.ctx.strokeRect(x0, y0, w, h);

    // Card label
    this.drawLabel(x0, y0, `Slot ${card.slot}`, OVERLAY_COLORS.card);

    // Draw regions (sprite, type1, type2)
    this.drawRegion('sprite', card, x0, y0, w, h, scale);
    this.drawRegion('type1', card, x0, y0, w, h, scale);
    this.drawRegion('type2', card, x0, y0, w, h, scale);

    // Draw stat boxes and arrows
    this.drawStatBoxes(card, x0, y0, w, h, scale);
    this.drawStatArrows(card, x0, y0, w, h, scale);
  }

  drawRegion(regionName, card, cardX, cardY, cardW, cardH, scale) {
    const regionConfig = CARD_LAYOUT_CONFIG.regions[regionName];
    if (!regionConfig) return;

    const rx = regionConfig.rx;
    const ry = regionConfig.ry;
    const size = regionConfig.size;

    const x = cardX + rx * cardW;
    const y = cardY + ry * cardH;
    const w = size * scale;
    const h = size * scale;

    // Get region color from OVERLAY_COLORS
    const color = OVERLAY_COLORS[regionName] || "#FFFFFF";

    // Draw region border
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 1.5;
    this.ctx.strokeRect(x, y, w, h);

    // Draw label
    this.drawLabel(x, y, regionName, color, 10);
  }

  drawStatBoxes(card, cardX, cardY, cardW, cardH, scale) {
    const config = CARD_LAYOUT_CONFIG.stat_boxes;
    if (!config) return;

    const color = "#C8C800";
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 1;

    const boxW = config.box_w * cardW;
    const boxH = config.box_h * cardH;

    // Left stat boxes
    const leftX = cardX + config.left_x * cardW;
    config.y_tops.forEach(yTop => {
      const y = cardY + yTop * cardH;
      this.ctx.strokeRect(leftX, y, boxW, boxH);
    });

    // Right stat boxes
    const rightX = cardX + config.right_x * cardW;
    config.y_tops.forEach(yTop => {
      const y = cardY + yTop * cardH;
      this.ctx.strokeRect(rightX, y, boxW, boxH);
    });
  }

  drawStatArrows(card, cardX, cardY, cardW, cardH, scale) {
    const arrows = CARD_LAYOUT_CONFIG.stat_arrows;
    if (!arrows) return;

    const color = "#64C8FF";
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 1;

    arrows.forEach(arrow => {
      const x = cardX + arrow.x * cardW;
      const y = cardY + arrow.y * cardH;
      // Convert size from pixels to relative (assuming 738px card width)
      const sizeRel = arrow.size / 738;
      const size = sizeRel * cardW;
      this.ctx.strokeRect(x, y, size, size);
    });
  }

  drawLabel(x, y, text, color, fontSize = 12) {
    // Draw background box
    this.ctx.font = `bold ${fontSize}px Arial, sans-serif`;
    const metrics = this.ctx.measureText(text);
    const textWidth = metrics.width;
    const textHeight = fontSize;

    const padding = 3;
    const boxX = Math.max(x, 0);
    const boxY = Math.max(y - textHeight - padding * 2, 0);
    const boxW = textWidth + padding * 2;
    const boxH = textHeight + padding * 2;

    // Draw background
    this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    this.ctx.fillRect(boxX, boxY, boxW, boxH);

    // Draw border
    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(boxX, boxY, boxW, boxH);

    // Draw text
    this.ctx.fillStyle = '#FFFFFF';
    this.ctx.textBaseline = 'top';
    this.ctx.fillText(text, boxX + padding, boxY + padding);
  }

  toggle() {
    if (this.isVisible) {
      this.hide();
    } else {
      this.show();
    }
  }

  show() {
    this.isVisible = true;
    this.canvas.style.display = 'block';
    document.getElementById('btn-show-layout').classList.add('active');
    document.getElementById('layout-controls').style.display = 'block';

    // Initialize display values from config
    if (CARD_LAYOUT_CONFIG && CARD_LAYOUT_CONFIG.layout) {
      document.getElementById('top-x-value').textContent = CARD_LAYOUT_CONFIG.layout.top_x;
      document.getElementById('top-y-value').textContent = CARD_LAYOUT_CONFIG.layout.top_y;
    }

    // Close opponent layout when showing this
    if (opponentLayoutOverlay) {
      opponentLayoutOverlay.hide();
    }

    this.updateCanvasSize();
    this.draw();
  }

  hide() {
    this.isVisible = false;
    this.canvas.style.display = 'none';
    document.getElementById('btn-show-layout').classList.remove('active');
    document.getElementById('layout-controls').style.display = 'none';
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
  }

  // 调整坐标
  adjustCoordinate(key, delta) {
    if (!CARD_LAYOUT_CONFIG || !CARD_LAYOUT_CONFIG.layout) return;

    const value = CARD_LAYOUT_CONFIG.layout[key];
    CARD_LAYOUT_CONFIG.layout[key] = value + delta;

    // 更新UI显示
    const displayId = key === 'top_x' ? 'top-x-value' : 'top-y-value';
    document.getElementById(displayId).textContent = CARD_LAYOUT_CONFIG.layout[key];

    // 立即重绘
    this.draw();
  }
}

/**
 * Opponent Team Layout Overlay
 */
class OpponentTeamOverlay {
  constructor() {
    this.canvas = document.getElementById('opponent-layout-canvas');
    this.video = document.getElementById('video');

    if (!this.canvas || !this.video) {
      return;
    }

    this.ctx = this.canvas.getContext('2d');
    this.isVisible = false;
    this.animationFrameId = null;

    this.setupCanvas();
    this.setupVideoListeners();
  }

  setupCanvas() {
    if (this.video.readyState >= 2) {
      this.updateCanvasSize();
    }
  }

  setupVideoListeners() {
    this.video.addEventListener('loadedmetadata', () => this.updateCanvasSize());
    this.video.addEventListener('play', () => this.updateCanvasSize());
    this.video.addEventListener('resize', () => this.updateCanvasSize());

    const observer = new ResizeObserver(() => this.updateCanvasSize());
    const container = this.video.parentElement;
    observer.observe(container);
  }

  updateCanvasSize() {
    const container = this.video.parentElement;
    const rect = container.getBoundingClientRect();

    this.canvas.width = rect.width;
    this.canvas.height = rect.height;

    if (this.isVisible) {
      this.draw();
    }
  }

  getScaleFactor() {
    if (!this.video.videoWidth || !this.video.videoHeight) {
      return 1;
    }

    const canvasRect = this.canvas.getBoundingClientRect();
    const videoAspect = this.video.videoWidth / this.video.videoHeight;
    const canvasAspect = canvasRect.width / canvasRect.height;

    if (videoAspect > canvasAspect) {
      return canvasRect.height / this.video.videoHeight;
    } else {
      return canvasRect.width / this.video.videoWidth;
    }
  }

  getVideoOffset() {
    const canvasRect = this.canvas.getBoundingClientRect();
    const scale = this.getScaleFactor();
    const scaledWidth = this.video.videoWidth * scale;
    const scaledHeight = this.video.videoHeight * scale;

    return {
      x: (canvasRect.width - scaledWidth) / 2,
      y: (canvasRect.height - scaledHeight) / 2,
      scale: scale,
    };
  }

  draw() {
    const { x: offsetX, y: offsetY, scale } = this.getVideoOffset();

    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    if (scale <= 0) return;

    const slots = generateOpponentTeamSlots();
    slots.forEach((slot) => {
      this.drawSlot(slot, offsetX, offsetY, scale);
    });

    if (this.isVisible) {
      this.animationFrameId = requestAnimationFrame(() => this.draw());
    }
  }

  drawSlot(slot, offsetX, offsetY, scale) {
    // Draw main slot frame (same as drawCard)
    const x0 = offsetX + slot.x * scale;
    const y0 = offsetY + slot.y * scale;
    const w = slot.w * scale;
    const h = slot.h * scale;

    // Slot border
    this.ctx.strokeStyle = OPP_OVERLAY_COLORS.slot;
    this.ctx.lineWidth = 2;
    this.ctx.strokeRect(x0, y0, w, h);

    // Slot label
    this.drawLabel(x0, y0, `Slot ${slot.slot}`, OPP_OVERLAY_COLORS.slot);

    // Draw regions (same as drawRegion in my team)
    this.drawOpponentRegion('sprite', slot, x0, y0, w, h);
    this.drawOpponentRegion('type1', slot, x0, y0, w, h);
    this.drawOpponentRegion('type2', slot, x0, y0, w, h);
  }

  drawOpponentRegion(regionName, slot, slotX, slotY, slotW, slotH) {
    const regionConfig = OPPONENT_TEAM_LAYOUT_CONFIG.slot_regions[regionName];
    if (!regionConfig) return;

    // Calculate position based on normalized coordinates (rx0/ry0 to rx1/ry1)
    const x = slotX + regionConfig.rx0 * slotW;
    const y = slotY + regionConfig.ry0 * slotH;
    const w = (regionConfig.rx1 - regionConfig.rx0) * slotW;
    const h = (regionConfig.ry1 - regionConfig.ry0) * slotH;

    const color = OPP_OVERLAY_COLORS[regionName] || "#FFFFFF";

    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 1.5;
    this.ctx.strokeRect(x, y, w, h);

    this.drawLabel(x, y, regionName, color, 10);
  }

  drawLabel(x, y, text, color, fontSize = 12) {
    this.ctx.font = `bold ${fontSize}px Arial, sans-serif`;
    const metrics = this.ctx.measureText(text);
    const textWidth = metrics.width;
    const textHeight = fontSize;

    const padding = 3;
    const boxX = Math.max(x, 0);
    const boxY = Math.max(y - textHeight - padding * 2, 0);
    const boxW = textWidth + padding * 2;
    const boxH = textHeight + padding * 2;

    this.ctx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    this.ctx.fillRect(boxX, boxY, boxW, boxH);

    this.ctx.strokeStyle = color;
    this.ctx.lineWidth = 1;
    this.ctx.strokeRect(boxX, boxY, boxW, boxH);

    this.ctx.fillStyle = '#FFFFFF';
    this.ctx.textBaseline = 'top';
    this.ctx.fillText(text, boxX + padding, boxY + padding);
  }

  toggle() {
    if (this.isVisible) {
      this.hide();
    } else {
      this.show();
    }
  }

  show() {
    this.isVisible = true;
    this.canvas.style.display = 'block';
    document.getElementById('btn-show-opponent-layout')?.classList.add('active');
    document.getElementById('opponent-layout-controls').style.display = 'block';

    // Initialize display values from config
    if (OPPONENT_TEAM_LAYOUT_CONFIG && OPPONENT_TEAM_LAYOUT_CONFIG.slot_layout) {
      document.getElementById('opponent-top-x-value').textContent = OPPONENT_TEAM_LAYOUT_CONFIG.slot_layout.x0;
      document.getElementById('opponent-top-y-value').textContent = OPPONENT_TEAM_LAYOUT_CONFIG.slot_layout.y0;
    }

    // Close my team layout when showing this
    if (layoutOverlay) {
      layoutOverlay.hide();
    }

    this.updateCanvasSize();
    this.draw();
  }

  hide() {
    this.isVisible = false;
    this.canvas.style.display = 'none';
    document.getElementById('btn-show-opponent-layout')?.classList.remove('active');
    document.getElementById('opponent-layout-controls').style.display = 'none';
    if (this.animationFrameId) {
      cancelAnimationFrame(this.animationFrameId);
    }
  }

  adjustCoordinate(key, delta) {
    if (!OPPONENT_TEAM_LAYOUT_CONFIG || !OPPONENT_TEAM_LAYOUT_CONFIG.slot_layout) return;

    const slotCfg = OPPONENT_TEAM_LAYOUT_CONFIG.slot_layout;
    const configKey = key === 'top_x' ? 'x0' : 'y0';
    const value = slotCfg[configKey];
    const newValue = value + delta;
    slotCfg[configKey] = newValue;

    const displayId = key === 'top_x' ? 'opponent-top-x-value' : 'opponent-top-y-value';
    document.getElementById(displayId).textContent = newValue;

    this.draw();
  }
}

// Global instances
let layoutOverlay = null;
let opponentLayoutOverlay = null;

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', async () => {
  await loadCardLayoutConfig();
  await loadOpponentTeamLayoutConfig();
  layoutOverlay = new LayoutOverlay();
  opponentLayoutOverlay = new OpponentTeamOverlay();
});

// Toggle function called from HTML button
function toggleLayoutOverlay() {
  if (layoutOverlay) {
    layoutOverlay.toggle();
  }
}

// Toggle opponent team layout overlay
function toggleOpponentLayoutOverlay() {
  if (opponentLayoutOverlay) {
    opponentLayoutOverlay.toggle();
  }
}

// 调整 top_y 坐标
function adjustTopY(delta) {
  if (layoutOverlay) {
    layoutOverlay.adjustCoordinate('top_y', delta);
  }
}

// 调整 top_x 坐标
function adjustTopX(delta) {
  if (layoutOverlay) {
    layoutOverlay.adjustCoordinate('top_x', delta);
  }
}

// 调整对方队伍 top_y 坐标
function adjustOpponentTopY(delta) {
  if (opponentLayoutOverlay) {
    opponentLayoutOverlay.adjustCoordinate('top_y', delta);
  }
}

// 调整对方队伍 top_x 坐标
function adjustOpponentTopX(delta) {
  if (opponentLayoutOverlay) {
    opponentLayoutOverlay.adjustCoordinate('top_x', delta);
  }
}

// 保存配置到JSON
async function saveLayoutConfig() {
  if (!CARD_LAYOUT_CONFIG) {
    return;
  }

  const btn = document.getElementById('save-layout-btn');
  btn.classList.add('saving');
  btn.textContent = '💾 保存中...';

  try {
    const response = await fetch('/api/save-layout-config', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(CARD_LAYOUT_CONFIG),
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || `HTTP error! status: ${response.status}`);
    }

    btn.classList.remove('saving');
    btn.classList.add('saved');
    btn.textContent = '✓ 已保存';

    setTimeout(() => {
      btn.classList.remove('saved');
      btn.textContent = '💾 保存配置';
    }, 2000);

  } catch (error) {
    btn.classList.remove('saving');
    btn.textContent = '❌ 保存失败';

    setTimeout(() => {
      btn.textContent = '💾 保存配置';
    }, 2000);
  }
}

// 保存对方队伍配置到JSON
async function saveOpponentLayoutConfig() {
  if (!OPPONENT_TEAM_LAYOUT_CONFIG) {
    return;
  }

  const btn = document.getElementById('save-opponent-layout-btn');
  btn.classList.add('saving');
  btn.textContent = '💾 保存中...';

  try {
    const response = await fetch('/api/save-opponent-layout-config', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(OPPONENT_TEAM_LAYOUT_CONFIG),
    });

    const result = await response.json();

    if (!response.ok) {
      throw new Error(result.error || `HTTP error! status: ${response.status}`);
    }

    btn.classList.remove('saving');
    btn.classList.add('saved');
    btn.textContent = '✓ 已保存';

    setTimeout(() => {
      btn.classList.remove('saved');
      btn.textContent = '💾 保存配置';
    }, 2000);

  } catch (error) {
    btn.classList.remove('saving');
    btn.textContent = '❌ 保存失败';

    setTimeout(() => {
      btn.textContent = '💾 保存配置';
    }, 2000);
  }
}
