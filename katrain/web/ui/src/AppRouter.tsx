import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ThemeProvider, CssBaseline } from '@mui/material';
import { zenTheme } from './theme';
import { AuthProvider } from './context/AuthContext';
import { SettingsProvider } from './context/SettingsContext';
import ZenModeApp from './ZenModeApp';

// Code-split: kiosk and galaxy bundles load independently
const GalaxyApp = lazy(() => import('./GalaxyApp'));
const KioskApp = lazy(() => import('./kiosk/KioskApp'));
const VideoRecorderPage = lazy(() => import('./pages/VideoRecorderPage'));

const AppRouter = () => {
  return (
    <ThemeProvider theme={zenTheme}>
      <CssBaseline />
      <BrowserRouter>
        <AuthProvider>
          <SettingsProvider>
            <Suspense fallback={null}>
              <Routes>
                <Route path="/kiosk/*" element={<KioskApp />} />
                <Route path="/galaxy/*" element={<GalaxyApp />} />
                <Route path="/record" element={<VideoRecorderPage />} />
                <Route path="/*" element={<ZenModeApp />} />
              </Routes>
            </Suspense>
          </SettingsProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  );
};

export default AppRouter;
