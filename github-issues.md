# GitHub Issues

## Issue 1: Speed Control Buttons Enhancement

### Description
Add additional speed control buttons to the speed axis UI for more granular control over speed calculations.

### Changes
- Added `×2` and `÷2` buttons for speed modifier mode selection
- Added `速度+1` (Speed +1) and `速度-1` (Speed -1) buttons for speed level adjustment
- Added `重置` (Reset) button to reset all speed states
- All speed control buttons are mutually exclusive

### Files Modified
- `pokepilot/ui/index.html`: Added 4 new buttons to speed-axis-controls
- `pokepilot/ui/team.js`: Added state variables and handler functions

### Implementation Details

**New State Variables:**
```javascript
let speedModifierState = {
    active: null,  // null | 'x2' | 'div2'
    _pendingLevelDelta: undefined,
    _pendingLevelMode: false
};
let speedLevels = {};  // key = "side-index", value = level (-6 to +6)
```

**New Functions:**
- `toggleSpeedModifier(mode)`: Toggle ×2/÷2 mode
- `adjustSpeedLevel(delta)`: Enter speed level adjustment mode
- `applySpeedModifierToPokemon(side, index)`: Apply modifier or level to pokemon
- `resetSpeedModifiers()`: Reset all speed states

### Related
- Mutually exclusive button behavior
- Click pokemon to apply modification
- Auto-reset button state after application

---

## Issue 2: Opponent Speed Range Edge Dragging

### Description
Enable users to drag the min/max endpoints of opponent speed bars to adjust the speed range.

### Changes
- Added `startOppEdgeDrag()` function to initiate edge dragging
- Added `onOppEdgeDragMove()` function to handle drag movement
- Added `updateOppSpeedRowVisual()` function to update visual elements
- Added `stopOppEdgeDrag()` function to end dragging

### Files Modified
- `pokepilot/ui/team.js`: Added drag handling functions
- `pokepilot/ui/style.css`: Added `.speed-opp-min-text` and `.speed-opp-max-text` styles

### Drag Limitations
- Cannot drag below theoretical minimum (baseMin)
- Cannot drag above theoretical maximum (baseMax)
- Affected by: Tailwind × Speed Modifier × Speed Level

### Implementation Details

```javascript
function onOppEdgeDragMove(event) {
    const pointerRaw = speedFieldState.opp_tailwind ? pointerSpeed / 2 : pointerSpeed;
    const pointerUnmodified = pointerRaw / (modifierMultiplier * levelMultiplier);

    if (edge === 'min') {
        const minLimit = baseMin;
        const maxLimit = baseMax * modifierMultiplier * levelMultiplier;
        newMin = Math.max(minLimit, Math.min(pointerUnmodified, maxLimit));
    } else {
        const minLimit = baseMin * modifierMultiplier * levelMultiplier;
        const maxLimit = baseMax * modifierMultiplier * levelMultiplier;
        newMax = Math.max(minLimit, Math.min(pointerUnmodified, maxLimit));
    }
}
```

### Related
- Sprite resets to center after edge drag
- Edge points have `ew-resize` cursor
- `event.stopPropagation()` to prevent row click interference

---

## Issue 3: Speed Calculation with All Modifiers

### Description
Implement comprehensive speed calculation that accounts for all modifier factors: Tailwind, Speed Modifiers (×2/÷2), and Speed Levels.

### Formula

**Display Value:**
```
displayValue = originalValue × tailwind(×2) × modifier(×2/÷2) × levelMultiplier
levelMultiplier = 1 + level × 0.5
```

**Drag Storage:**
```
pointerRaw = displayValue / tailwindFactor (2 when tailwind active)
pointerUnmodified = pointerRaw / (modifier × levelMultiplier)
storedValue = clamp(pointerUnmodified, baseMin, baseMax)
```

### Speed Level Multipliers

| Level | Multiplier |
|-------|------------|
| -6 | 0.25A |
| -5 | 0.5A |
| -4 | 0.75A |
| -3 | 1.0A |
| -2 | 1.25A |
| -1 | 1.5A |
| 0 | A (base) |
| +1 | 1.5A |
| +2 | 2.0A |
| +3 | 2.5A |
| +4 | 3.0A |
| +5 | 3.5A |
| +6 | 4.0A |

### Files Modified
- `pokepilot/ui/team.js`: Updated `getEffectiveSpeed()`, `onOppEdgeDragMove()`
- `pokepilot/ui/team.js`: Updated `fillOppSection()` to use `oppCustomSpeedRange`

### Related
- Opponent speed bar displays min-max range
- Custom range stored in `oppCustomSpeedRange[globalIndex]`
- All modifiers properly affect both display and drag calculations

---

## Issue 4: FillOppSection Custom Range Support

### Description
Update `fillOppSection` function to use custom speed ranges from `oppCustomSpeedRange` instead of only base values.

### Changes
```javascript
const custom = oppCustomSpeedRange[globalIndex];
const displayMin = custom ? custom.min : baseMin;
const displayMax = custom ? custom.max : baseMax;

const sMin = getEffectiveSpeed(displayMin, speedFieldState.opp_tailwind, p);
const sMax = getEffectiveSpeed(displayMax, speedFieldState.opp_tailwind, p);
```

### Bug Fixed
Previously, when user dragged min/max and then toggled tailwind, the custom range was ignored and base values were used instead.

### Files Modified
- `pokepilot/ui/team.js`: Updated `fillOppSection()` function

---

## Issue 5: Sprite Position Clamping

### Description
Fix issue where sprite position could exceed 100%, causing it to disappear from view when tailwind is active.

### Changes
```javascript
spriteEl.style.left = `${Math.min(pctMid, 100)}%`;
```

### Files Modified
- `pokepilot/ui/team.js`: Updated sprite position assignment in `fillOppSection()`

---

## Issue 6: Edge Drag Event Propagation Fix

### Description
Fix issue where clicking and dragging min/max endpoints triggered row click events, causing incorrect behavior when tailwind is active.

### Changes
Added `event.stopPropagation()` to mousedown handlers:
```javascript
minEl.addEventListener('mousedown', (event) => {
    event.stopPropagation();
    startOppEdgeDrag(event, globalIndex, 'min', ...);
});
```

### Files Modified
- `pokepilot/ui/team.js`: Updated `fillOppSection()` mousedown handlers

---

## Issue 7: Sprite Drag Range Using Custom Range

### Description
Update sprite drag behavior to use custom speed range instead of base values.

### Changes
```javascript
spriteEl.addEventListener('mousedown', (event) => {
    const custom = oppCustomSpeedRange[globalIndex];
    const effectiveMin = custom ? custom.min : baseMin;
    const effectiveMax = custom ? custom.max : baseMax;
    // ... calculate percentages using effectiveMin/effectiveMax
});
```

### Files Modified
- `pokepilot/ui/team.js`: Updated sprite mousedown handler

---

## Test Cases (Initial Values 100, 200)

### Case 1: Basic Drag
- Initial (100, 200) → Drag min to 120 → Drag max to 180
- Expected: (120, 180)

### Case 2: Tailwind + Drag Min
- Initial (100, 200) → Tailwind shows (200, 400) → Drag min to 300 → Cancel tailwind
- Expected: (150, 200)

### Case 3: Tailwind + Drag Max
- Initial (100, 200) → Tailwind shows (200, 400) → Drag max to 350 → Cancel tailwind
- Expected: (100, 175)

### Case 4: Drag + Tailwind
- Initial (100, 200) → Drag min to 120 → Tailwind
- Expected: (240, 400)

### Case 5: ×2 Modifier
- Initial (100, 200) → ×2 shows (200, 400) → Drag min to 300 → Cancel ×2
- Expected: (150, 200)

### Case 6: ×2 + Tailwind
- Initial (100, 200) → ×2 shows (200, 400) → Tailwind
- Expected: (400, 800)

### Case 7: ×2 + Tailwind + Drag + Cancel
- Initial (100, 200) → ×2 → Tailwind shows (400, 800) → Drag min to 600 → Cancel ×2 → Cancel tailwind
- Expected: (150, 200)

### Case 8: Speed +1 Modifier
- Initial (100, 200) → Speed +1 shows (150, 300) → Drag min to 180 → Cancel
- Expected: (180, 200)

### Case 9: Speed +1 + Tailwind
- Initial (100, 200) → Speed +1 → Tailwind
- Expected: (300, 600)

### Case 10: Speed +1 + Tailwind + Drag Max + Cancel
- Initial (100, 200) → Speed +1 → Tailwind shows (300, 600) → Drag max to 450 → Cancel +1 → Cancel tailwind
- Expected: (150, 150)

---

## Summary of Changes

| File | Changes |
|------|---------|
| index.html | Added 4 new buttons (×2, ÷2, 速度+1, 速度-1, 重置) |
| team.js | New state variables (speedModifierState, speedLevels, oppCustomSpeedRange) |
| team.js | Modified getEffectiveSpeed() to include speed level |
| team.js | New functions (adjustSpeedLevel, applySpeedModifierToPokemon, etc.) |
| team.js | New drag functions (startOppEdgeDrag, onOppEdgeDragMove, etc.) |
| team.js | Fixed fillOppSection to use oppCustomSpeedRange |
| team.js | Fixed edge drag event propagation |
| team.js | Fixed sprite position clamping |
| style.css | Added .speed-opp-min-text, .speed-opp-max-text styles |