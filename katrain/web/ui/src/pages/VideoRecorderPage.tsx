/**
 * VideoRecorderPage — Full-screen page for recording tutorial lecture videos.
 *
 * Used by Playwright (headless) to capture 3D Go board animation + subtitles.
 * The Python script (generate_video.py) injects timeline data via
 * window.__RECORDING_DATA and triggers playback via a "startRecording" event.
 *
 * Move numbers and letters are HTML overlays with perspective-correct sizing
 * (projected stone radius determines font size per stone). This avoids troika
 * CDN dependency issues in headless environments while looking natural.
 *
 * Route: /record (outside Galaxy layout, no sidebar)
 */
import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import { Vector3 } from 'three';
import type { RootState } from '@react-three/fiber';
import type { GameState, PlayerInfo } from '../api';
import { gridToWorld, gridToSurface, STONE_RADIUS } from '../components/Board3D/constants';

// Lazy-load Board3D (same pattern as GamePage)
const Board3D = lazy(() => import('../components/Board3D'));

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TimelineInitialStone {
  color: 'B' | 'W';
  pos: [number, number];
}

interface TimelineMove {
  number: number;
  color: 'B' | 'W';
  pos: [number, number];
  trigger_ms: number;
}

interface TimelineSubtitle {
  start_ms: number;
  end_ms: number;
  text: string;
}

interface TimelineLetter {
  letter: string;
  pos: [number, number];
  trigger_ms: number;
}

interface Timeline {
  figure_id: number;
  figure_label: string;
  board_size: number;
  viewport?: {
    col: number;
    row: number;
    cols?: number;
    rows?: number;
  } | null;
  initial_stones: TimelineInitialStone[];
  moves: TimelineMove[];
  letters?: TimelineLetter[];
  subtitles: TimelineSubtitle[];
  total_duration_ms: number;
  audio_url: string;
  polar_angle?: number;
}

interface MoveNumberOverlay {
  x: number;
  y: number;
  number: number;
  isBlack: boolean;
  fontSize: number;
}

interface LetterOverlay {
  x: number;
  y: number;
  letter: string;
  fontSize: number;
}

declare global {
  interface Window {
    __RECORDING_DATA?: Timeline;
    __RECORDING_DONE?: boolean;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const DEFAULT_PLAYER: PlayerInfo = {
  player_type: 'human',
  player_subtype: '',
  name: '',
  calculated_rank: null,
  periods_used: 0,
  main_time_used: 0,
};

function makeGameState(
  boardSize: number,
  stones: [string, [number, number] | null, number | null, number | null][],
  lastMove: [number, number] | null,
  nodeIndex: number,
): GameState {
  return {
    game_id: 'recording',
    board_size: [boardSize, boardSize],
    komi: 6.5,
    handicap: 0,
    ruleset: 'chinese',
    current_node_id: nodeIndex,
    current_node_index: nodeIndex,
    history: [],
    player_to_move: 'B',
    stones,
    last_move: lastMove,
    prisoner_count: { B: 0, W: 0 },
    analysis: null,
    commentary: '',
    is_root: nodeIndex === 0,
    is_pass: false,
    end_result: null,
    children: [],
    ghost_stones: [],
    players_info: { B: DEFAULT_PLAYER, W: DEFAULT_PLAYER },
    note: '',
    ui_state: {
      show_children: false,
      show_dots: false,
      show_hints: false,
      show_policy: false,
      show_ownership: false,
      show_move_numbers: false,
      show_coordinates: true,
      zen_mode: false,
    },
    language: 'zh',
  };
}

function computeCamera(
  polarAngle: number = 0.15,
): { position: [number, number, number]; target: [number, number, number]; polarAngle: number } {
  const target: [number, number, number] = [0, 1.2, 0];
  const distance = 33.3;
  const theta = polarAngle * Math.PI;
  const y = distance * Math.cos(theta) + target[1];
  const z = distance * Math.sin(theta) + target[2];
  return { position: [0, y, z], target, polarAngle };
}

/** Project 3D world position to 2D screen coordinates. */
function projectToScreen(
  worldPos: [number, number, number],
  camera: RootState['camera'],
  canvasW: number,
  canvasH: number,
): { x: number; y: number } {
  const v = new Vector3(...worldPos);
  v.project(camera);
  return {
    x: (v.x * 0.5 + 0.5) * canvasW,
    y: (-v.y * 0.5 + 0.5) * canvasH,
  };
}

/** Compute apparent stone radius in pixels by projecting stone center + edge. */
function computeApparentRadius(
  worldPos: [number, number, number],
  camera: RootState['camera'],
  canvasW: number,
  canvasH: number,
): number {
  const center = projectToScreen(worldPos, camera, canvasW, canvasH);
  const edgePos: [number, number, number] = [worldPos[0] + STONE_RADIUS, worldPos[1], worldPos[2]];
  const edge = projectToScreen(edgePos, camera, canvasW, canvasH);
  return Math.abs(edge.x - center.x);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function VideoRecorderPage() {
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [gameState, setGameState] = useState<GameState | null>(null);
  const [subtitle, setSubtitle] = useState('');
  const [moveNumberOverlays, setMoveNumberOverlays] = useState<MoveNumberOverlay[]>([]);
  const [letterOverlays, setLetterOverlays] = useState<LetterOverlay[]>([]);
  const [status, setStatus] = useState('Waiting for recording data...');

  const placedMovesRef = useRef<number>(0);
  const stonesRef = useRef<[string, [number, number] | null, number | null, number | null][]>([]);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);
  const r3fStateRef = useRef<RootState | null>(null);

  const handleCanvasReady = useCallback((state: RootState) => {
    r3fStateRef.current = state;
    (window as any).__r3fState = state;
    console.log('Canvas ready, R3F state captured for direct rendering');
  }, []);

  useEffect(() => {
    return () => { timersRef.current.forEach(clearTimeout); };
  }, []);

  const startPlayback = useCallback((tl: Timeline) => {
    const bs = tl.board_size;
    const flipRow = (pos: [number, number]): [number, number] => [pos[0], bs - 1 - pos[1]];

    const initialStones: [string, [number, number] | null, number | null, number | null][] =
      (tl.initial_stones || []).map((s) => [s.color, flipRow(s.pos), null, null]);

    stonesRef.current = initialStones;
    placedMovesRef.current = 0;
    setGameState(makeGameState(bs, initialStones, null, 0));
    setSubtitle('');
    setMoveNumberOverlays([]);
    setLetterOverlays([]);
    setStatus('Ready');

    (window as any).__setFrame = (time_ms: number) => {
      const visibleMoves = tl.moves.filter((m) => m.trigger_ms <= time_ms);
      const moveStones: [string, [number, number] | null, number | null, number | null][] =
        visibleMoves.map((m) => [m.color, flipRow(m.pos), null, m.number]);

      const stones = [...initialStones, ...moveStones];
      const lastMove = visibleMoves.length > 0
        ? flipRow(visibleMoves[visibleMoves.length - 1].pos)
        : null;

      stonesRef.current = stones;
      placedMovesRef.current = visibleMoves.length;
      setGameState(makeGameState(bs, stones, lastMove, visibleMoves.length));

      // Compute perspective-correct overlay positions and sizes
      const state = r3fStateRef.current;
      if (state) {
        const { camera, gl } = state;
        const canvasW = gl.domElement.clientWidth;
        const canvasH = gl.domElement.clientHeight;

        // Move numbers (on stones) — size scales with perspective
        if (visibleMoves.length > 0) {
          setMoveNumberOverlays(visibleMoves.map((m) => {
            const [col, row] = flipRow(m.pos);
            const worldPos = gridToWorld(col, row, bs);
            const screen = projectToScreen(worldPos, camera, canvasW, canvasH);
            const apparentR = computeApparentRadius(worldPos, camera, canvasW, canvasH);
            const digits = String(m.number).length;
            const fontSize = apparentR * (digits === 1 ? 1.1 : 0.85);
            return { x: screen.x, y: screen.y, number: m.number, isBlack: m.color === 'B', fontSize };
          }));
        } else {
          setMoveNumberOverlays([]);
        }

        // Letter annotations (on board surface) — same perspective scaling
        const visibleLetters = (tl.letters || []).filter((lt) => lt.trigger_ms <= time_ms);
        if (visibleLetters.length > 0) {
          setLetterOverlays(visibleLetters.map((lt) => {
            const [col, row] = flipRow(lt.pos);
            const worldPos = gridToSurface(col, row, bs);
            const screen = projectToScreen(worldPos, camera, canvasW, canvasH);
            const apparentR = computeApparentRadius(
              gridToWorld(col, row, bs), camera, canvasW, canvasH,
            );
            return { x: screen.x, y: screen.y, letter: lt.letter, fontSize: apparentR * 1.2 };
          }));
        } else {
          setLetterOverlays([]);
        }
      } else {
        setMoveNumberOverlays([]);
        setLetterOverlays([]);
      }

      const activeSub = tl.subtitles.find(
        (s) => time_ms >= s.start_ms && time_ms < s.end_ms,
      );
      setSubtitle(activeSub?.text ?? '');
    };

    window.__RECORDING_DONE = false;
    (window as any).__RECORDING_READY = true;

    (window as any).__forceRender = () => {
      const state = r3fStateRef.current;
      if (state) {
        const { gl, scene, camera } = state;
        gl.render(scene, camera);
      }
    };

    console.log('Recording page ready for frame capture');
  }, []);

  useEffect(() => {
    const handler = () => {
      const data = window.__RECORDING_DATA;
      if (data) { setTimeline(data); startPlayback(data); }
      else { console.error('startRecording fired but no __RECORDING_DATA found'); }
    };
    window.addEventListener('startRecording', handler);
    return () => window.removeEventListener('startRecording', handler);
  }, [startPlayback]);

  useEffect(() => {
    if (window.__RECORDING_DATA) {
      setTimeline(window.__RECORDING_DATA);
      startPlayback(window.__RECORDING_DATA);
    }
  }, [startPlayback]);

  const camera = timeline
    ? computeCamera(timeline.polar_angle ?? 0.15)
    : computeCamera(0.15);

  const noop = useCallback(() => {}, []);
  // Numbers rendered as perspective-scaled HTML overlays (troika doesn't work in headless).
  // Drop effect enabled with adaptive 24fps capture during drops.
  const analysisToggles = { coords: false, stoneDropEffect: true, numbers: false };

  return (
    <div
      style={{
        width: '100vw',
        height: '100vh',
        background: '#0f0f0f',
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Board area */}
      <div style={{ flex: 1, position: 'relative' }}>
        {gameState ? (
          <Suspense fallback={null}>
            <Board3D
              gameState={gameState}
              onMove={noop}
              analysisToggles={analysisToggles}
              cameraPosition={camera.position}
              cameraTarget={camera.target}
              disableControls
              fixedPolarAngle={camera.polarAngle}
              frameloop="always"
              onCanvasReady={handleCanvasReady}
            />
          </Suspense>
        ) : (
          <div
            style={{
              width: '100%',
              height: '100%',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#666',
              fontSize: '24px',
              fontFamily: 'sans-serif',
            }}
          >
            {status}
          </div>
        )}

        {/* Move numbers — perspective-scaled to match stone size */}
        {moveNumberOverlays.map(({ x, y, number, isBlack, fontSize }) => (
          <div
            key={`mn-${number}`}
            style={{
              position: 'absolute',
              left: x,
              top: y,
              transform: 'translate(-50%, -50%)',
              color: isBlack ? '#fff' : '#000',
              fontSize,
              fontWeight: 'bold',
              fontFamily: '"Noto Sans SC", "Noto Sans", sans-serif',
              lineHeight: 1,
              pointerEvents: 'none',
              textShadow: isBlack
                ? '0 0 3px rgba(0,0,0,0.9), 0 0 1px rgba(0,0,0,1)'
                : '0 0 3px rgba(255,255,255,0.9), 0 0 1px rgba(255,255,255,1)',
            }}
          >
            {number}
          </div>
        ))}

        {/* Letter annotations — perspective-scaled, red */}
        {letterOverlays.map(({ x, y, letter, fontSize }) => (
          <div
            key={`lt-${letter}`}
            style={{
              position: 'absolute',
              left: x,
              top: y,
              transform: 'translate(-50%, -50%)',
              color: '#d32f2f',
              fontSize,
              fontWeight: 'bold',
              fontFamily: '"Noto Sans SC", "Noto Sans", sans-serif',
              lineHeight: 1,
              pointerEvents: 'none',
              textShadow: '0 0 4px rgba(0,0,0,0.8), 0 0 2px rgba(0,0,0,0.9)',
            }}
          >
            {letter}
          </div>
        ))}
      </div>

      {/* Subtitle bar */}
      <div
        style={{
          background: subtitle ? 'rgba(0,0,0,0.75)' : 'transparent',
          padding: '28px 64px',
          textAlign: 'center',
          minHeight: '110px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transition: 'background 0.3s',
        }}
      >
        <span
          style={{
            color: '#fff',
            fontSize: '40px',
            fontFamily: '"Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif',
            lineHeight: 1.6,
            textShadow: '0 2px 8px rgba(0,0,0,0.8)',
          }}
        >
          {subtitle}
        </span>
      </div>
    </div>
  );
}
