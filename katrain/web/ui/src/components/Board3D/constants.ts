// ===== Board Geometry =====
// BOARD_SURFACE_Y equals boardHeight: slab goes from y=0 to y=boardHeight

const GRID_SPACING = 1.0;
const BOARD_PADDING = 0.8;
export const STONE_RADIUS = 0.42;
export const STONE_HEIGHT = 0.22;
export const BOARD_SURFACE_Y = 1.20;
export const DROP_HEIGHT = 5;

// ===== Z-offset constants (prevent z-fighting) =====
export const SURFACE_EPSILON = 0.005;   // Flat overlays sitting on the board surface
export const OVERLAY_OFFSET = 0.01;     // Elements slightly above board (click plane, text)
export const ABOVE_STONE = 0.005;       // Markers on top of stones (LastMove ring, EvalDots)

export interface BoardDimensions {
  boardSize: number;
  gridSpacing: number;
  boardExtent: number;
  boardWidth: number;
  boardHeight: number;
}

export function getBoardDimensions(boardSize: number): BoardDimensions {
  const boardExtent = (boardSize - 1) * GRID_SPACING;
  const boardWidth = boardExtent + BOARD_PADDING * 2;
  return {
    boardSize,
    gridSpacing: GRID_SPACING,
    boardExtent,
    boardWidth,
    boardHeight: 1.2,
  };
}

/**
 * Convert grid (col, row) to 3D world [x, y, z].
 * col → x axis, row → z axis (inverted so row=0 is near camera), y = board surface + stone height.
 * col maps to GameState x, row maps to GameState y.
 *
 * Z is inverted vs X: row=0 maps to +z (near camera at positive z),
 * matching the 2D Board.tsx where row=0 is drawn at the bottom (near player).
 */
export function gridToWorld(col: number, row: number, boardSize: number): [number, number, number] {
  const extent = (boardSize - 1) * GRID_SPACING;
  const halfExtent = extent / 2;
  return [
    -halfExtent + col * GRID_SPACING,
    BOARD_SURFACE_Y + STONE_HEIGHT,
    halfExtent - row * GRID_SPACING,
  ];
}

/**
 * Convert world (x, z) to grid {col, row}, or null if out of bounds.
 * Z is inverted: positive z maps to row=0, negative z maps to row=boardSize-1.
 */
export function worldToGrid(worldX: number, worldZ: number, boardSize: number): { col: number; row: number } | null {
  const extent = (boardSize - 1) * GRID_SPACING;
  const halfExtent = extent / 2;
  const col = Math.round((worldX + halfExtent) / GRID_SPACING);
  const row = Math.round((halfExtent - worldZ) / GRID_SPACING);
  if (col >= 0 && col < boardSize && row >= 0 && row < boardSize) {
    return { col, row };
  }
  return null;
}

/**
 * Grid position on the board surface (y = BOARD_SURFACE_Y + SURFACE_EPSILON).
 * Used for flat overlays that sit on the board, not on stones.
 * Z is inverted to match gridToWorld orientation.
 */
export function gridToSurface(col: number, row: number, boardSize: number): [number, number, number] {
  const extent = (boardSize - 1) * GRID_SPACING;
  const halfExtent = extent / 2;
  return [
    -halfExtent + col * GRID_SPACING,
    BOARD_SURFACE_Y + SURFACE_EPSILON,
    halfExtent - row * GRID_SPACING,
  ];
}

// ===== Font for drei <Text> — local file to avoid CDN dependency =====
export const TEXT_FONT = '/assets/fonts/NotoSans-Regular.ttf';

// ===== Eval Colors (matches Board.tsx EVAL_COLORS) =====

export const EVAL_COLORS = [
  '#964196', // Purple - blunder (>12)
  '#e16b5c', // Red - big mistake (>6)
  '#d4a574', // Warm orange - mistake (>3)
  '#e8c864', // Yellow - inaccuracy (>1.5)
  '#abc864', // Light green - ok (>0.5)
  '#4a6b5c', // Jade green - excellent (<=0.5)
] as const;

export const EVAL_THRESHOLDS = [12, 6, 3, 1.5, 0.5, 0] as const;

export function getEvalColor(scoreLoss: number): string {
  for (let i = 0; i < EVAL_THRESHOLDS.length; i++) {
    if (scoreLoss >= EVAL_THRESHOLDS[i]) return EVAL_COLORS[i];
  }
  return EVAL_COLORS[5];
}

// ===== Star Points =====

export function getStarPoints(boardSize: number): [number, number][] {
  const stars =
    boardSize === 19 ? [3, 9, 15] :
    boardSize === 13 ? [3, 6, 9] :
    boardSize === 9 ? [2, 4, 6] : [];
  const points: [number, number][] = [];
  for (const x of stars) {
    for (const y of stars) {
      points.push([x, y]);
    }
  }
  return points;
}

// ===== Coordinate Labels =====

const LETTERS = 'ABCDEFGHJKLMNOPQRSTUVWXYZ';

export function getColumnLabel(col: number): string {
  return LETTERS[col] || '';
}

export function getRowLabel(row: number): string {
  return (row + 1).toString();
}
