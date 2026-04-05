/**
 * VideoRecorderPage — Full-screen page for recording tutorial lecture videos.
 *
 * Used by Playwright (headless) to capture 3D Go board animation + subtitles.
 * The Python script (generate_video.py) injects timeline data via
 * window.__RECORDING_DATA and triggers playback via a "startRecording" event.
 *
 * Route: /record (outside Galaxy layout, no sidebar)
 */
import { useState, useEffect, useCallback, useRef, lazy, Suspense } from 'react';
import type { GameState, PlayerInfo } from '../api';

// Lazy-load Board3D (same pattern as GamePage)
const Board3D = lazy(() => import('../components/Board3D'));

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

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
  moves: TimelineMove[];
  subtitles: TimelineSubtitle[];
  total_duration_ms: number;
  audio_url: string;
  polar_angle?: number; // Camera tilt as fraction of π (e.g., 0.33 = 0.33π)
}

// Extend Window for Playwright communication
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

/**
 * Compute camera position and target for video recording.
 * Always centers on the full board. polarAngle controls tilt
 * (fraction of π — 0.05 = bird's eye, 0.38 = most tilted).
 */
function computeCamera(
  polarAngle: number = 0.15,
): { position: [number, number, number]; target: [number, number, number]; polarAngle: number } {
  const target: [number, number, number] = [0, 1.2, 0];

  // Camera distance from target (same as default ~33 units)
  const distance = 33.3;
  const theta = polarAngle * Math.PI;

  const y = distance * Math.cos(theta) + target[1];
  const z = distance * Math.sin(theta) + target[2];

  return {
    position: [0, y, z],
    target,
    polarAngle,
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function VideoRecorderPage() {
  const [timeline, setTimeline] = useState<Timeline | null>(null);
  const [gameState, setGameState] = useState<GameState | null>(null);
  const [subtitle, setSubtitle] = useState('');
  const [status, setStatus] = useState('Waiting for recording data...');

  const placedMovesRef = useRef<number>(0);
  const stonesRef = useRef<[string, [number, number] | null, number | null, number | null][]>([]);
  const timersRef = useRef<ReturnType<typeof setTimeout>[]>([]);

  // Clean up timers on unmount
  useEffect(() => {
    return () => {
      timersRef.current.forEach(clearTimeout);
    };
  }, []);

  const startPlayback = useCallback((tl: Timeline) => {
    const bs = tl.board_size;

    // Initialize empty board so Three.js starts loading
    stonesRef.current = [];
    placedMovesRef.current = 0;
    setGameState(makeGameState(bs, [], null, 0));
    setSubtitle('');
    setStatus('Ready');

    // Expose deterministic frame-setting API for Playwright
    // Python calls window.__setFrame(time_ms) for each frame
    (window as any).__setFrame = (time_ms: number) => {
      // Determine which stones should be visible at this time
      const visibleMoves = tl.moves.filter((m) => m.trigger_ms <= time_ms);
      const stones: [string, [number, number] | null, number | null, number | null][] =
        visibleMoves.map((m) => [m.color, m.pos, null, m.number]);

      // Find the last placed move (for last_move indicator + drop animation trigger)
      const lastMove = visibleMoves.length > 0
        ? visibleMoves[visibleMoves.length - 1].pos as [number, number]
        : null;

      stonesRef.current = stones;
      placedMovesRef.current = visibleMoves.length;
      setGameState(makeGameState(bs, stones, lastMove, visibleMoves.length));

      // Find active subtitle at this time
      const activeSub = tl.subtitles.find(
        (s) => time_ms >= s.start_ms && time_ms < s.end_ms
      );
      setSubtitle(activeSub?.text ?? '');
    };

    // Signal readiness
    window.__RECORDING_DONE = false;
    (window as any).__RECORDING_READY = true;

    // Force canvas repaint after each frame set (headless mode may throttle rAF)
    (window as any).__forceRender = () => {
      window.dispatchEvent(new Event('resize'));
    };

    console.log('Recording page ready for frame capture');
  }, []);

  // Listen for startRecording event (triggered by Playwright after injecting data)
  useEffect(() => {
    const handler = () => {
      const data = window.__RECORDING_DATA;
      if (data) {
        setTimeline(data);
        startPlayback(data);
      } else {
        console.error('startRecording fired but no __RECORDING_DATA found');
      }
    };
    window.addEventListener('startRecording', handler);
    return () => window.removeEventListener('startRecording', handler);
  }, [startPlayback]);

  // Also check on mount if data is already present (for manual testing)
  useEffect(() => {
    if (window.__RECORDING_DATA) {
      const data = window.__RECORDING_DATA;
      setTimeline(data);
      startPlayback(data);
    }
  }, [startPlayback]);

  const camera = timeline
    ? computeCamera(timeline.polar_angle ?? 0.15)
    : computeCamera(0.15);

  const noop = useCallback(() => {}, []);
  const analysisToggles = { coords: true, stoneDropEffect: true, numbers: true };

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
