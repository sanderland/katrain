export interface PlayerInfo {
  player_type: string;
  player_subtype: string;
  name: string;
  calculated_rank: string | null;
  periods_used: number;
  main_time_used: number;
}

export interface GameState {
  game_id: string;
  board_size: [number, number];
  komi: number;
  handicap: number;
  ruleset: string;
  current_node_id: number;
  current_node_index: number;
  history: { node_id: number; score: number | null; winrate: number | null }[];
  player_to_move: string;
  stones: [string, [number, number] | null, number | null, number | null][];
  last_move: [number, number] | null;
  prisoner_count: { B: number; W: number };
  analysis: any;
  commentary: string;
  is_root: boolean;
  is_pass: boolean;
  end_result: string | null;
  children: [string, [number, number] | null][];
  ghost_stones: [string, [number, number] | null][];
  players_info: { B: PlayerInfo; W: PlayerInfo };
  note: string;
  ui_state: {
    show_children: boolean;
    show_dots: boolean;
    show_hints: boolean;
    show_policy: boolean;
    show_ownership: boolean;
    show_move_numbers: boolean;
    show_coordinates: boolean;
    zen_mode: boolean;
  };
  sockets_count?: number;
  timer?: {
    paused: boolean;
    main_time_used: number;
    current_node_time_used: number;
    next_player_periods_used: number;
    settings: {
      main_time: number;
      byo_length: number;
      byo_periods: number;
      minimal_use: number;
      sound: boolean;
    };
  };
  language: string;
  count_min_moves?: number;
  engine?: "local" | "cloud";
  trainer_settings?: {
    eval_thresholds: number[];
    show_dots: boolean[];
    save_feedback: boolean[];
    save_marks: boolean[];
    eval_show_ai: boolean;
    lock_ai: boolean;
    top_moves_show: string;
    max_top_moves_on_board: number;
    low_visits: number;
    fast_visits?: number;
    max_visits?: number;
  };
}

export interface SessionResponse {
  session_id: string;
  state: GameState;
}

// --- Cross-platform play types ---

export interface PlatformInfo {
  platform: string;
  connected: boolean;
  supports_live_play: boolean;
  supports_automatch: boolean;
  supports_rooms: boolean;
  supports_seek_graph: boolean;
  saved_username?: string;
}

export interface PlatformStatusResponse {
  platforms: PlatformInfo[];
}

export interface PlatformUser {
  user_id: string;
  username: string;
  rank: string;
  status: string;
}

export interface PlatformClockState {
  black_time: Record<string, any>;
  white_time: Record<string, any>;
  current_player: "B" | "W";
  paused?: boolean;
}

export interface VisionStatusResponse {
  enabled: boolean;
  camera_connected: boolean;
  pose_locked: boolean;
  sync_state: string;
  bound_session_id: string | null;
}

async function apiPost(path: string, payload: any, token?: string) {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const response = await fetch(path, {
    method: "POST",
    headers,
    body: JSON.stringify(payload || {}),
  });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`Request failed ${response.status}: ${body}`);
  }
  return response.json();
}

export const API = {
  createSession: (): Promise<SessionResponse> => apiPost("/api/session", {}),
  getState: async (sessionId: string): Promise<SessionResponse> => {
    const params = new URLSearchParams({ session_id: sessionId });
    const response = await fetch(`/api/state?${params.toString()}`);
    if (!response.ok) throw new Error("Failed to get state");
    return { session_id: sessionId, state: (await response.json()).state };
  },
  playMove: (sessionId: string, coords: { x: number; y: number } | null, token?: string): Promise<SessionResponse> =>
    apiPost("/api/move", {
      session_id: sessionId,
      coords: coords ? [coords.x, coords.y] : null,
      pass_move: coords === null,
    }, token),
  undo: (sessionId: string, nTimes: number | string = 1): Promise<SessionResponse> =>
    apiPost("/api/undo", { session_id: sessionId, n_times: nTimes }),
  redo: (sessionId: string, nTimes: number = 1): Promise<SessionResponse> =>
    apiPost("/api/redo", { session_id: sessionId, n_times: nTimes }),
  newGame: (sessionId: string, settings?: any): Promise<SessionResponse> =>
    apiPost("/api/new-game", { session_id: sessionId, ...settings }),
  gameSetup: (sessionId: string, mode: string, settings: any): Promise<SessionResponse> =>
    apiPost("/api/game/setup", { session_id: sessionId, mode, settings }),
  aiMove: (sessionId: string): Promise<SessionResponse> =>
    apiPost("/api/ai-move", { session_id: sessionId }),
  navigate: (sessionId: string, nodeId?: number): Promise<SessionResponse> =>
    apiPost("/api/nav", { session_id: sessionId, node_id: nodeId }),
  loadSGF: (sessionId: string, sgf: string, skipAnalysis: boolean = false): Promise<SessionResponse> =>
    apiPost("/api/sgf/load", { session_id: sessionId, sgf, skip_analysis: skipAnalysis }),
  saveSGF: async (sessionId: string): Promise<{ sgf: string }> => {
    const params = new URLSearchParams({ session_id: sessionId });
    const response = await fetch(`/api/sgf/save?${params.toString()}`);
    if (!response.ok) throw new Error("Failed to save SGF");
    return response.json();
  },
  getConfig: async (sessionId: string, setting: string): Promise<any> => {
    const params = new URLSearchParams({ session_id: sessionId, setting });
    const response = await fetch(`/api/config?${params.toString()}`);
    if (!response.ok) throw new Error("Failed to get config");
    return (await response.json()).value;
  },
  updateConfig: (sessionId: string, setting: string, value: any): Promise<SessionResponse> =>
    apiPost("/api/config", { session_id: sessionId, setting, value }),
  updateConfigBulk: (sessionId: string, updates: Record<string, any>): Promise<SessionResponse> =>
    apiPost("/api/config/bulk", { session_id: sessionId, updates }),
  updatePlayer: (sessionId: string, bw: string, playerType?: string, playerSubtype?: string, name?: string): Promise<SessionResponse> =>
    apiPost("/api/player", { session_id: sessionId, bw, player_type: playerType, player_subtype: playerSubtype, name }),
  swapPlayers: (sessionId: string): Promise<SessionResponse> =>
    apiPost("/api/player/swap", { session_id: sessionId }),
  resign: (sessionId: string): Promise<SessionResponse> =>
    apiPost("/api/resign", { session_id: sessionId }),
  timeout: (sessionId: string): Promise<SessionResponse> =>
    apiPost("/api/timeout", { session_id: sessionId }),
  requestCount: (sessionId: string, token?: string): Promise<any> =>
    apiPost("/api/count/request", { session_id: sessionId }, token),
  respondCount: (sessionId: string, accept: boolean, token?: string): Promise<any> =>
    apiPost("/api/count/respond", { session_id: sessionId, accept }, token),
  pauseTimer: (sessionId: string): Promise<SessionResponse> =>
    apiPost("/api/timer/pause", { session_id: sessionId }),
  rotate: (sessionId: string): Promise<SessionResponse> =>
    apiPost("/api/rotate", { session_id: sessionId }),
  showPV: (sessionId: string, pv: string): Promise<SessionResponse> =>
    apiPost("/api/analysis/show-pv", { session_id: sessionId, pv }),
  clearPV: (sessionId: string): Promise<SessionResponse> =>
    apiPost("/api/analysis/clear-pv", { session_id: sessionId }),
  findMistake: (sessionId: string, fn: "redo" | "undo"): Promise<SessionResponse> =>
    apiPost("/api/nav/mistake", { session_id: sessionId, fn }),
  setMode: (sessionId: string, mode: string): Promise<SessionResponse> =>
    apiPost("/api/mode", { session_id: sessionId, mode }),
  deleteNode: (sessionId: string, nodeId?: number): Promise<SessionResponse> =>
    apiPost("/api/node/delete", { session_id: sessionId, node_id: nodeId }),
  pruneBranch: (sessionId: string, nodeId?: number): Promise<SessionResponse> =>
    apiPost("/api/node/prune", { session_id: sessionId, node_id: nodeId }),
  makeMainBranch: (sessionId: string, nodeId?: number): Promise<SessionResponse> =>
    apiPost("/api/node/make-main", { session_id: sessionId, node_id: nodeId }),
  toggleCollapse: (sessionId: string, nodeId?: number): Promise<SessionResponse> =>
    apiPost("/api/node/toggle-collapse", { session_id: sessionId, node_id: nodeId }),
  toggleUI: (sessionId: string, setting: string): Promise<SessionResponse> =>
    apiPost("/api/ui/toggle", { session_id: sessionId, setting }),
  analyze: (sessionId: string, payload: any): Promise<any> =>
    apiPost("/api/v1/analysis/analyze", { session_id: sessionId, payload }),
  analyzeGame: (sessionId: string, visits?: number, mistakes_only: boolean = false): Promise<SessionResponse> =>
    apiPost("/api/analysis/game", { session_id: sessionId, visits, mistakes_only }),
  analysisScan: (sessionId: string, visits?: number): Promise<SessionResponse> =>
    apiPost("/api/analysis/scan", { session_id: sessionId, visits }),
  quickAnalyze: (params: {
    moves: string[][]; initial_stones?: string[][]; board_size?: number; komi?: number; rules?: string; max_visits?: number;
  }): Promise<any> =>
    apiPost("/api/v1/analysis/quick-analyze", params),
  analysisProgress: async (sessionId: string): Promise<{ session_id: string; analyzed: number; total: number }> => {
    const response = await fetch(`/api/analysis/progress?session_id=${sessionId}`);
    if (!response.ok) throw new Error("Failed to fetch analysis progress");
    return response.json();
  },
  getGameReport: (sessionId: string, depth_filter?: number[]): Promise<any> => 
    apiPost("/api/analysis/report", { session_id: sessionId, depth_filter }),
  getAIConstants: async (): Promise<{ strategies: string[], options: Record<string, any>, key_properties: string[], default_strategy: string }> => {
    const response = await fetch('/api/ai-constants');
    if (!response.ok) throw new Error("Failed to fetch AI constants");
    return response.json();
  },
  estimateRank: (strategy: string, settings: any): Promise<{ rank: string }> =>
    apiPost("/api/ai/estimate-rank", { strategy, settings }),
  getTranslations: async (lang: string) => {
    const params = new URLSearchParams({ lang });
    const response = await fetch(`/api/translations?${params.toString()}`);
    if (!response.ok) throw new Error("Failed to fetch translations");
    return response.json();
  },
  login: async (username: string, password: string): Promise<{ access_token: string, token_type: string }> => {
    const response = await fetch("/api/v1/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Login failed ${response.status}: ${body}`);
    }
    return response.json();
  },
  register: async (username: string, password: string): Promise<any> => {
    const response = await fetch("/api/v1/auth/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      const body = await response.text();
      throw new Error(`Registration failed ${response.status}: ${body}`);
    }
    return response.json();
  },
  getMe: async (token: string): Promise<any> => {
    const response = await fetch("/api/v1/auth/me", {
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Failed to get user info");
    return response.json();
  },
  followUser: async (token: string, username: string): Promise<any> => {
    const response = await fetch(`/api/v1/users/follow/${username}`, {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Failed to follow user");
    return response.json();
  },
  unfollowUser: async (token: string, username: string): Promise<any> => {
    const response = await fetch(`/api/v1/users/follow/${username}`, {
      method: "DELETE",
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Failed to unfollow user");
    return response.json();
  },
  getFollowing: async (token: string): Promise<any[]> => {
    const response = await fetch("/api/v1/users/following", {
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Failed to get following list");
    return response.json();
  },
  getFollowers: async (token: string): Promise<any[]> => {
    const response = await fetch("/api/v1/users/followers", {
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Failed to get followers list");
    return response.json();
  },
  leaveMultiplayerGame: (sessionId: string, token: string): Promise<any> =>
    apiPost("/api/multiplayer/leave", { session_id: sessionId }, token),

  // Vision API
  visionStatus: (): Promise<VisionStatusResponse> =>
    fetch("/api/v1/vision/status").then(r => r.json()),
  visionConfirmPoseLock: (): Promise<void> =>
    apiPost("/api/v1/vision/pose-lock/confirm", {}),
  visionBind: (sessionId: string): Promise<void> =>
    apiPost("/api/v1/vision/bind", { session_id: sessionId }),
  visionUnbind: (): Promise<void> =>
    apiPost("/api/v1/vision/unbind", {}),
  visionResetSync: (): Promise<void> =>
    apiPost("/api/v1/vision/sync/reset", {}),
  visionSetupMode: (targetBoard: number[][]): Promise<void> =>
    apiPost("/api/v1/vision/setup-mode", { target_board: targetBoard }),

  logout: async (token: string): Promise<any> => {
    const response = await fetch("/api/v1/auth/logout", {
      method: "POST",
      headers: { "Authorization": `Bearer ${token}` },
    });
    if (!response.ok) {
      // Don't throw on logout failure - still proceed with local cleanup
      console.warn("Server logout failed, proceeding with local cleanup");
    }
    return response.ok ? response.json() : { status: "local_only" };
  },

  // --- Cross-platform online play ---
  platformLogin: (platform: string, credentials: { username: string; password: string }, token: string) =>
    apiPost(`/api/v1/platforms/${platform}/login`, credentials, token),
  platformLogout: async (platform: string, token: string) => {
    const response = await fetch(`/api/v1/platforms/${platform}/logout`, {
      method: "DELETE",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error(`Logout failed: ${response.status}`);
    return response.json();
  },
  platformStatus: async (token: string): Promise<PlatformStatusResponse> => {
    const response = await fetch("/api/v1/platforms/status", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Failed to get platform status");
    return response.json();
  },
  platformUsers: async (platform: string, token: string, query?: string): Promise<{ users: PlatformUser[] }> => {
    const params = query ? `?q=${encodeURIComponent(query)}` : '';
    const response = await fetch(`/api/v1/platforms/${platform}/users${params}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Failed to get users");
    return response.json();
  },
  platformRooms: async (platform: string, token: string) => {
    const response = await fetch(`/api/v1/platforms/${platform}/rooms`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Failed to get rooms");
    return response.json();
  },
  platformChallenges: async (platform: string, token: string) => {
    const response = await fetch(`/api/v1/platforms/${platform}/challenges`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok) throw new Error("Failed to get challenges");
    return response.json();
  },
  platformSendChallenge: (platform: string, data: object, token: string) =>
    apiPost(`/api/v1/platforms/${platform}/challenge`, data, token),
  platformAcceptChallenge: (platform: string, challengeId: string, token: string) =>
    apiPost(`/api/v1/platforms/${platform}/challenge/accept`, { challenge_id: challengeId }, token),
  platformDeclineChallenge: (platform: string, challengeId: string, token: string) =>
    apiPost(`/api/v1/platforms/${platform}/challenge/decline`, { challenge_id: challengeId }, token),
  platformStartAutomatch: (platform: string, prefs: object, token: string) =>
    apiPost(`/api/v1/platforms/${platform}/automatch/start`, prefs, token),
  platformCancelAutomatch: (platform: string, token: string) =>
    apiPost(`/api/v1/platforms/${platform}/automatch/cancel`, {}, token),
};
