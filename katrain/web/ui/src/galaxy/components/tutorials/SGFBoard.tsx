export interface SGFPayload {
  size: number;
  stones: {
    B: [number, number][];
    W: [number, number][];
  };
  labels?: Record<string, string>;
  letters?: Record<string, string>;
  shapes?: Record<string, string>;
  highlights?: [number, number][];
  viewport?: { col: number; row: number; size?: number; cols?: number; rows?: number } | null;
}

interface SGFBoardProps {
  payload: SGFPayload;
  maxMoveStep?: number;
  showFullBoard?: boolean;
  onClick?: (col: number, row: number) => void;
}

const CELL = 32;
const MARGIN = CELL * 0.75;
const STONE_R = CELL * 0.44;
const HOSHI_R = 3;

const HOSHI_19: [number, number][] = [
  [3, 3], [9, 3], [15, 3],
  [3, 9], [9, 9], [15, 9],
  [3, 15], [9, 15], [15, 15],
];

export default function SGFBoard({ payload, maxMoveStep, showFullBoard, onClick }: SGFBoardProps) {
  const { size, stones, labels = {}, letters = {}, shapes = {}, highlights = [], viewport } = payload;

  // Viewport: support rectangular {col, row, cols, rows} and square {col, row, size}
  const vp = showFullBoard
    ? { col: 0, row: 0, cols: size, rows: size }
    : viewport
      ? { col: viewport.col, row: viewport.row, cols: viewport.cols ?? viewport.size ?? size, rows: viewport.rows ?? viewport.size ?? size }
      : { col: 0, row: 0, cols: size, rows: size };

  const vpCols = vp.cols;
  const vpRows = vp.rows;

  const svgW = MARGIN * 2 + (vpCols - 1) * CELL;
  const svgH = MARGIN * 2 + (vpRows - 1) * CELL;

  const toSvg = (col: number, row: number) => ({
    x: MARGIN + (col - vp.col) * CELL,
    y: MARGIN + (row - vp.row) * CELL,
  });

  const inViewport = (col: number, row: number) =>
    col >= vp.col && col < vp.col + vpCols &&
    row >= vp.row && row < vp.row + vpRows;

  // Check if a stone should be shown based on maxMoveStep
  const shouldShowStone = (col: number, row: number): boolean => {
    if (maxMoveStep === undefined) return true;
    const label = labels[`${col},${row}`];
    if (!label) return true; // unlabeled stones always shown
    const num = parseInt(label, 10);
    if (isNaN(num)) return true; // non-numeric labels always shown
    return num <= maxMoveStep;
  };

  // Grid lines
  const gridLines: React.ReactNode[] = [];
  for (let i = 0; i < vpRows; i++) {
    const y = MARGIN + i * CELL;
    gridLines.push(
      <line key={`h${i}`} x1={MARGIN} y1={y} x2={MARGIN + (vpCols - 1) * CELL} y2={y} stroke="#7a5c2e" strokeWidth={0.8} />
    );
  }
  for (let i = 0; i < vpCols; i++) {
    const x = MARGIN + i * CELL;
    gridLines.push(
      <line key={`v${i}`} x1={x} y1={MARGIN} x2={x} y2={MARGIN + (vpRows - 1) * CELL} stroke="#7a5c2e" strokeWidth={0.8} />
    );
  }

  // Hoshi dots
  const hoshiDots = HOSHI_19
    .filter(([c, r]) => inViewport(c, r))
    .map(([c, r]) => {
      const { x, y } = toSvg(c, r);
      return <circle key={`hoshi-${c}-${r}`} cx={x} cy={y} r={HOSHI_R} fill="#7a5c2e" />;
    });

  // Stones and labels
  const stoneEls: React.ReactNode[] = [];
  const labelEls: React.ReactNode[] = [];

  for (const [col, row] of stones.B) {
    if (!inViewport(col, row) || !shouldShowStone(col, row)) continue;
    const { x, y } = toSvg(col, row);
    const key = `B-${col}-${row}`;
    stoneEls.push(
      <circle key={key} cx={x} cy={y} r={STONE_R} fill="#1a1a1a" stroke="#000" strokeWidth={0.5} />
    );
    const label = labels[`${col},${row}`];
    if (label && (maxMoveStep === undefined || parseInt(label, 10) <= (maxMoveStep ?? Infinity))) {
      labelEls.push(
        <text key={`lbl-${key}`} x={x} y={y + 1} textAnchor="middle" dominantBaseline="middle"
          fontSize={STONE_R * 1.1} fill="#fff" fontWeight="bold" fontFamily="sans-serif">
          {label}
        </text>
      );
    }
  }

  for (const [col, row] of stones.W) {
    if (!inViewport(col, row) || !shouldShowStone(col, row)) continue;
    const { x, y } = toSvg(col, row);
    const key = `W-${col}-${row}`;
    stoneEls.push(
      <circle key={key} cx={x} cy={y} r={STONE_R} fill="#f0f0f0" stroke="#555" strokeWidth={0.8} />
    );
    const label = labels[`${col},${row}`];
    if (label && (maxMoveStep === undefined || parseInt(label, 10) <= (maxMoveStep ?? Infinity))) {
      labelEls.push(
        <text key={`lbl-${key}`} x={x} y={y + 1} textAnchor="middle" dominantBaseline="middle"
          fontSize={STONE_R * 1.1} fill="#333" fontWeight="bold" fontFamily="sans-serif">
          {label}
        </text>
      );
    }
  }

  // Letters (on empty intersections)
  const letterEls: React.ReactNode[] = [];
  for (const [coordStr, letter] of Object.entries(letters)) {
    const [col, row] = coordStr.split(',').map(Number);
    if (!inViewport(col, row)) continue;
    const { x, y } = toSvg(col, row);
    letterEls.push(
      <text key={`letter-${coordStr}`} x={x} y={y + 1} textAnchor="middle"
        dominantBaseline="middle" fontSize={STONE_R * 1.2} fill="#d32f2f"
        fontWeight="bold" fontFamily="sans-serif">
        {letter}
      </text>
    );
  }

  // Shapes (on empty intersections)
  const shapeEls: React.ReactNode[] = [];
  for (const [coordStr, shape] of Object.entries(shapes)) {
    const [col, row] = coordStr.split(',').map(Number);
    if (!inViewport(col, row)) continue;
    const { x, y } = toSvg(col, row);
    const r = STONE_R * 0.5;
    if (shape === 'triangle') {
      const pts = `${x},${y - r} ${x - r * 0.866},${y + r * 0.5} ${x + r * 0.866},${y + r * 0.5}`;
      shapeEls.push(<polygon key={`shape-${coordStr}`} points={pts} fill="none" stroke="#1565c0" strokeWidth={2} />);
    } else if (shape === 'square') {
      shapeEls.push(<rect key={`shape-${coordStr}`} x={x - r} y={y - r} width={r * 2} height={r * 2}
        fill="none" stroke="#1565c0" strokeWidth={2} />);
    } else if (shape === 'circle') {
      shapeEls.push(<circle key={`shape-${coordStr}`} cx={x} cy={y} r={r}
        fill="none" stroke="#1565c0" strokeWidth={2} />);
    } else if (shape === 'cross') {
      const d = r * 0.7;
      shapeEls.push(
        <g key={`shape-${coordStr}`}>
          <line x1={x - d} y1={y - d} x2={x + d} y2={y + d} stroke="#1565c0" strokeWidth={2} />
          <line x1={x - d} y1={y + d} x2={x + d} y2={y - d} stroke="#1565c0" strokeWidth={2} />
        </g>
      );
    }
  }

  // Highlight triangles (on stones)
  const triangleEls = highlights
    .filter(([c, r]) => inViewport(c, r))
    .map(([col, row]) => {
      const { x, y } = toSvg(col, row);
      const r = STONE_R * 0.6;
      const pts = [
        `${x},${y - r}`,
        `${x - r * 0.866},${y + r * 0.5}`,
        `${x + r * 0.866},${y + r * 0.5}`,
      ].join(' ');
      const isBlack = stones.B.some(([c2, r2]) => c2 === col && r2 === row);
      return (
        <polygon key={`tri-${col}-${row}`} points={pts}
          fill="none" stroke={isBlack ? '#fff' : '#000'} strokeWidth={1.5} />
      );
    });

  // Click grid (when onClick is provided)
  const clickGrid: React.ReactNode[] = [];
  if (onClick) {
    for (let r = vp.row; r < vp.row + vpRows; r++) {
      for (let c = vp.col; c < vp.col + vpCols; c++) {
        const { x, y } = toSvg(c, r);
        clickGrid.push(
          <rect
            key={`click-${c}-${r}`}
            x={x - CELL / 2}
            y={y - CELL / 2}
            width={CELL}
            height={CELL}
            fill="transparent"
            style={{ cursor: 'crosshair' }}
            onClick={() => onClick(c, r)}
          />
        );
      }
    }
  }

  return (
    <svg
      viewBox={`0 0 ${svgW} ${svgH}`}
      width="100%"
      style={{ maxWidth: 500, display: 'block', background: '#dcb468', borderRadius: 4 }}
      aria-label="Go board diagram"
    >
      {gridLines}
      {hoshiDots}
      {stoneEls}
      {triangleEls}
      {letterEls}
      {shapeEls}
      {labelEls}
      {clickGrid}
    </svg>
  );
}
