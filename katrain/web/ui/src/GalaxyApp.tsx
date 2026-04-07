import { Routes, Route, Navigate } from 'react-router-dom';
import MainLayout from './galaxy/components/layout/MainLayout';
import Dashboard from './galaxy/pages/Dashboard';
import ResearchPage from './galaxy/pages/ResearchPage';
import PlayMenu from './galaxy/pages/PlayMenu';
import AiSetupPage from './galaxy/pages/AiSetupPage';
import GamePage from './galaxy/pages/GamePage';
import HvHLobbyPage from './galaxy/pages/HvHLobbyPage';
import GameRoomPage from './galaxy/pages/GameRoomPage';
import KifuLibraryPage from './galaxy/pages/KifuLibraryPage';
import LivePage from './galaxy/pages/live/LivePage';
import LiveMatchPage from './galaxy/pages/live/LiveMatchPage';
import TsumegoLevelsPage from './galaxy/pages/TsumegoLevelsPage';
import TsumegoCategoriesPage from './galaxy/pages/TsumegoCategoriesPage';
import TsumegoListPage from './galaxy/pages/TsumegoListPage';
import TsumegoUnitsPage from './galaxy/pages/TsumegoUnitsPage';
import TsumegoProblemPage from './galaxy/pages/TsumegoProblemPage';
import TutorialLandingPage from './galaxy/pages/tutorials/TutorialLandingPage';
import TutorialBooksPage from './galaxy/pages/tutorials/TutorialBooksPage';
import TutorialBookDetailPage from './galaxy/pages/tutorials/TutorialBookDetailPage';
import TutorialFigurePage from './galaxy/pages/tutorials/TutorialFigurePage';

const GalaxyApp = () => {
  console.log("GalaxyApp rendering");
  return (
    <Routes>
      <Route element={<MainLayout />}>
        <Route index element={<Dashboard />} />
        <Route path="play" element={<PlayMenu />} />
        <Route path="play/ai" element={<AiSetupPage />} />
        <Route path="play/game/:sessionId" element={<GamePage />} />
        <Route path="play/human" element={<HvHLobbyPage />} />
        <Route path="play/human/room/:sessionId" element={<GameRoomPage />} />
        <Route path="research" element={<ResearchPage />} />
        <Route path="kifu" element={<KifuLibraryPage />} />
        <Route path="live" element={<LivePage />} />
        <Route path="live/:matchId" element={<LiveMatchPage />} />
        <Route path="tsumego" element={<TsumegoLevelsPage />} />
        <Route path="tsumego/:level" element={<TsumegoCategoriesPage />} />
        <Route path="tsumego/:level/:category" element={<TsumegoUnitsPage />} />
        <Route path="tsumego/:level/:category/:unit" element={<TsumegoListPage />} />
        <Route path="tsumego/problem/:problemId" element={<TsumegoProblemPage />} />
        <Route path="tutorials" element={<TutorialLandingPage />} />
        <Route path="tutorials/:category" element={<TutorialBooksPage />} />
        <Route path="tutorials/book/:bookId" element={<TutorialBookDetailPage />} />
        <Route path="tutorials/section/:sectionId" element={<TutorialFigurePage />} />
        <Route path="*" element={<Navigate to="/galaxy" replace />} />
      </Route>
    </Routes>
  );
};

export default GalaxyApp;
