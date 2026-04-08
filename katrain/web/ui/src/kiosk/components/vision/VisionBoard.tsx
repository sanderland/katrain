import { useRef, useEffect } from 'react';

/**
 * Lightweight 19x19 board renderer that displays detected stone positions.
 * Props.board is a 19x19 matrix: 0=empty, 1=black, 2=white.
 */

const BOARD_COLOR = '#DCB35C';
const LINE_COLOR = '#333';
const STAR_POINTS_19 = [
  [3, 3], [3, 9], [3, 15],
  [9, 3], [9, 9], [9, 15],
  [15, 3], [15, 9], [15, 15],
];

interface VisionBoardProps {
  board: number[][] | null;
  boardSize?: number;
}

const VisionBoard = ({ board, boardSize = 19 }: VisionBoardProps) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const size = canvas.width;
    const margin = size * 0.04;
    const gridSize = (size - 2 * margin) / (boardSize - 1);

    // Background
    ctx.fillStyle = BOARD_COLOR;
    ctx.fillRect(0, 0, size, size);

    // Grid lines
    ctx.strokeStyle = LINE_COLOR;
    ctx.lineWidth = 1;
    for (let i = 0; i < boardSize; i++) {
      const pos = margin + i * gridSize;
      // Horizontal
      ctx.beginPath();
      ctx.moveTo(margin, pos);
      ctx.lineTo(size - margin, pos);
      ctx.stroke();
      // Vertical
      ctx.beginPath();
      ctx.moveTo(pos, margin);
      ctx.lineTo(pos, size - margin);
      ctx.stroke();
    }

    // Star points
    if (boardSize === 19) {
      ctx.fillStyle = LINE_COLOR;
      for (const [row, col] of STAR_POINTS_19) {
        const x = margin + col * gridSize;
        const y = margin + row * gridSize;
        ctx.beginPath();
        ctx.arc(x, y, gridSize * 0.12, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    // Stones
    if (board) {
      const stoneRadius = gridSize * 0.45;
      for (let row = 0; row < boardSize; row++) {
        for (let col = 0; col < boardSize; col++) {
          const val = board[row]?.[col];
          if (!val) continue;

          const x = margin + col * gridSize;
          const y = margin + row * gridSize;

          // Stone shadow
          ctx.fillStyle = 'rgba(0,0,0,0.2)';
          ctx.beginPath();
          ctx.arc(x + 1.5, y + 1.5, stoneRadius, 0, Math.PI * 2);
          ctx.fill();

          // Stone body
          const gradient = ctx.createRadialGradient(
            x - stoneRadius * 0.3, y - stoneRadius * 0.3, stoneRadius * 0.1,
            x, y, stoneRadius,
          );
          if (val === 1) {
            // Black
            gradient.addColorStop(0, '#555');
            gradient.addColorStop(1, '#111');
          } else {
            // White
            gradient.addColorStop(0, '#fff');
            gradient.addColorStop(1, '#ccc');
          }
          ctx.fillStyle = gradient;
          ctx.beginPath();
          ctx.arc(x, y, stoneRadius, 0, Math.PI * 2);
          ctx.fill();

          // White stone border
          if (val === 2) {
            ctx.strokeStyle = '#999';
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }
    }

    // "No data" placeholder
    if (!board) {
      ctx.fillStyle = 'rgba(0,0,0,0.3)';
      ctx.fillRect(0, 0, size, size);
      ctx.fillStyle = '#fff';
      ctx.font = `${size * 0.04}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.fillText('等待识别...', size / 2, size / 2);
    }
  }, [board, boardSize]);

  return (
    <canvas
      ref={canvasRef}
      width={400}
      height={400}
      style={{
        width: '100%',
        height: '100%',
        objectFit: 'contain',
        display: 'block',
      }}
    />
  );
};

export default VisionBoard;
