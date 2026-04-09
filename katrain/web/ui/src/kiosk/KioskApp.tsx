import { Routes, Route, Navigate } from 'react-router-dom';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { kioskTheme } from './theme';
import { useAuth } from '../context/AuthContext';
import { OrientationProvider } from './context/OrientationContext';
import { VisionProvider } from './context/VisionContext';
import RotationWrapper from './components/layout/RotationWrapper';
import KioskAuthGuard from './components/guards/KioskAuthGuard';
import KioskLayout from './components/layout/KioskLayout';
import LoginPage from './pages/LoginPage';
import PlaceholderPage from './pages/PlaceholderPage';
import PlayPage from './pages/PlayPage';
import AiSetupPage from './pages/AiSetupPage';
import GamePage from './pages/GamePage';
import TsumegoPage from './pages/TsumegoPage';
import TsumegoLevelPage from './pages/TsumegoLevelPage';
import TsumegoProblemPage from './pages/TsumegoProblemPage';
import ResearchPage from './pages/ResearchPage';
import KifuPage from './pages/KifuPage';
import LivePage from './pages/LivePage';
import LiveMatchPage from './pages/LiveMatchPage';
import LobbyPage from './pages/LobbyPage';
import SettingsPage from './pages/SettingsPage';
import VisionSetupPage from './pages/VisionSetupPage';
import PlatformConnectPage from './pages/PlatformConnectPage';
import PlatformLobbyPage from './pages/PlatformLobbyPage';

const KioskRoutes = () => {
  const { user } = useAuth();

  return (
    <Routes>
      {/* Public */}
      <Route path="login" element={<LoginPage />} />

      {/* Auth-protected */}
      <Route element={<KioskAuthGuard />}>
        {/* Fullscreen — no nav rail */}
        <Route path="play/ai/game/:sessionId" element={<GamePage />} />
        <Route path="play/pvp/local/game/:sessionId" element={<GamePage />} />
        <Route path="play/pvp/room/:sessionId" element={<GamePage />} />

        {/* Standard — with nav rail */}
        <Route element={<KioskLayout username={user?.username} />}>
          <Route index element={<Navigate to="play" replace />} />
          <Route path="play" element={<PlayPage />} />
          <Route path="play/ai/setup/:mode" element={<AiSetupPage />} />
          <Route path="play/pvp/setup" element={<PlaceholderPage />} />
          <Route path="play/pvp/lobby" element={<LobbyPage />} />
          <Route path="play/cross-platform" element={<PlatformConnectPage />} />
          <Route path="play/cross-platform/lobby" element={<PlatformLobbyPage />} />
          <Route path="tsumego" element={<TsumegoPage />} />
          <Route path="tsumego/:levelId" element={<TsumegoLevelPage />} />
          <Route path="tsumego/problem/:problemId" element={<TsumegoProblemPage />} />
          <Route path="research" element={<ResearchPage />} />
          <Route path="research/session/:sessionId" element={<GamePage />} />
          <Route path="kifu" element={<KifuPage />} />
          <Route path="kifu/:kifuId" element={<PlaceholderPage />} />
          <Route path="live" element={<LivePage />} />
          <Route path="live/:matchId" element={<LiveMatchPage />} />
          <Route path="vision/setup" element={<VisionSetupPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="play" replace />} />
        </Route>
      </Route>
    </Routes>
  );
};

const KioskApp = () => (
  <ThemeProvider theme={kioskTheme}>
    <CssBaseline />
    <OrientationProvider>
      <VisionProvider>
        <RotationWrapper>
          <KioskRoutes />
        </RotationWrapper>
      </VisionProvider>
    </OrientationProvider>
  </ThemeProvider>
);

export default KioskApp;
