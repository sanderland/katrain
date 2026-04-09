import { useEffect, useRef, useState, useCallback } from "react";
import type { PlatformClockState } from "../../api";

/** Platform WebSocket event types (from server → client). */
export type PlatformEvent =
  | { type: "platform_challenge"; platform: string; challenge: any }
  | { type: "platform_challenge_withdrawn"; platform: string; challenge_id: string }
  | { type: "platform_game_started"; platform: string; session_id: string; game: any }
  | { type: "platform_game_ended"; platform: string; game_id: string; result: string }
  | { type: "platform_status"; platform: string; connected: boolean }
  | { type: "platform_automatch_found"; platform: string; session_id: string; game: any }
  | { type: "platform_auth_expired"; platform: string }
  | { type: "platform_move_pending"; col: number; row: number }
  | { type: "platform_move_confirmed"; col: number; row: number; move_number: number }
  | { type: "platform_move_rejected"; reason: string }
  | { type: "platform_resync_required"; reason: string }
  | { type: "platform_resync_complete"; moves_recovered: number }
  | { type: "platform_phase_changed"; phase: string }
  | { type: "clock_update"; black_time: any; white_time: any; current_player: string; paused?: boolean };

export interface PlatformEventCallbacks {
  onChallenge?: (platform: string, challenge: any) => void;
  onGameStarted?: (platform: string, sessionId: string, game: any) => void;
  onGameEnded?: (platform: string, gameId: string, result: string) => void;
  onAutomatchFound?: (platform: string, sessionId: string, game: any) => void;
  onAuthExpired?: (platform: string) => void;
  onMovePending?: (col: number, row: number) => void;
  onMoveConfirmed?: (col: number, row: number, moveNumber: number) => void;
  onMoveRejected?: (reason: string) => void;
  onClockUpdate?: (clock: PlatformClockState) => void;
  onPhaseChanged?: (phase: string) => void;
}

/**
 * Hook for platform WebSocket events on the lobby or game session WebSocket.
 * Listens on an existing WebSocket ref for platform-specific event types.
 */
export function usePlatformEvents(
  wsRef: React.MutableRefObject<WebSocket | null>,
  callbacks: PlatformEventCallbacks
) {
  const [pendingMove, setPendingMove] = useState<{ col: number; row: number } | null>(null);
  const [clock, setClock] = useState<PlatformClockState | null>(null);
  const [gamePhase, setGamePhase] = useState<string>("playing");
  const [lastEvent, setLastEvent] = useState<PlatformEvent | null>(null);
  const cbRef = useRef(callbacks);
  cbRef.current = callbacks;

  const handleMessage = useCallback((event: MessageEvent) => {
    let data: PlatformEvent;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }

    // Only handle platform events
    if (!data.type?.startsWith("platform_") && data.type !== "clock_update") return;

    setLastEvent(data);

    switch (data.type) {
      case "platform_challenge":
        cbRef.current.onChallenge?.(data.platform, data.challenge);
        break;
      case "platform_game_started":
        cbRef.current.onGameStarted?.(data.platform, data.session_id, data.game);
        break;
      case "platform_game_ended":
        cbRef.current.onGameEnded?.(data.platform, data.game_id, data.result);
        break;
      case "platform_automatch_found":
        cbRef.current.onAutomatchFound?.(data.platform, data.session_id, data.game);
        break;
      case "platform_auth_expired":
        cbRef.current.onAuthExpired?.(data.platform);
        break;
      case "platform_move_pending":
        setPendingMove({ col: data.col, row: data.row });
        cbRef.current.onMovePending?.(data.col, data.row);
        break;
      case "platform_move_confirmed":
        setPendingMove(null);
        cbRef.current.onMoveConfirmed?.(data.col, data.row, data.move_number);
        break;
      case "platform_move_rejected":
        setPendingMove(null);
        cbRef.current.onMoveRejected?.(data.reason);
        break;
      case "platform_phase_changed":
        setGamePhase(data.phase);
        cbRef.current.onPhaseChanged?.(data.phase);
        break;
      case "clock_update":
        const clockState: PlatformClockState = {
          black_time: data.black_time,
          white_time: data.white_time,
          current_player: data.current_player as "B" | "W",
          paused: data.paused,
        };
        setClock(clockState);
        cbRef.current.onClockUpdate?.(clockState);
        break;
    }
  }, []);

  useEffect(() => {
    const ws = wsRef.current;
    if (!ws) return;
    ws.addEventListener("message", handleMessage);
    return () => ws.removeEventListener("message", handleMessage);
  }, [wsRef.current, handleMessage]);

  return { pendingMove, clock, gamePhase, lastEvent };
}
