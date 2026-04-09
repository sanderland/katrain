import { useEffect, useState } from 'react';
import {
  Box, Typography, Dialog, DialogTitle, DialogContent,
  DialogActions, Button, TextField, CircularProgress, Chip,
} from '@mui/material';
import { Login, Logout } from '@mui/icons-material';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from '../../hooks/useTranslation';
import { API, type PlatformInfo } from '../../api';

type LoginFieldConfig = {
  userLabel: string; userLabelCn: string;
  passLabel: string; passLabelCn: string;
  userType?: string;  // input type, default "text"
};

const PLATFORM_META: Record<string, { label: string; labelCn: string; color: string; login: LoginFieldConfig; comingSoon?: boolean }> = {
  ogs: {
    label: 'OGS', labelCn: 'OGS', color: '#4a90d9',
    login: { userLabel: 'Username', userLabelCn: '用户名', passLabel: 'Password', passLabelCn: '密码' },
  },
  fox: {
    label: 'Fox Weiqi', labelCn: '野狐围棋', color: '#e67e22',
    login: { userLabel: 'Username', userLabelCn: '用户名', passLabel: 'Password', passLabelCn: '密码' },
    comingSoon: true,
  },
  golaxy: {
    label: 'Golaxy', labelCn: '星阵围棋', color: '#2ecc71',
    login: { userLabel: 'Phone Number', userLabelCn: '手机号', passLabel: 'Verification Code', passLabelCn: '验证码', userType: 'tel' },
    comingSoon: true,
  },
};

const PlatformConnectPage = () => {
  const { t } = useTranslation();
  const { token } = useAuth();
  const navigate = useNavigate();
  const [platforms, setPlatforms] = useState<PlatformInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [loginDialog, setLoginDialog] = useState<string | null>(null);
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');

  const fetchStatus = async () => {
    if (!token) return;
    try {
      const data = await API.platformStatus(token);
      setPlatforms(data.platforms);
    } catch (e) {
      console.error('Failed to fetch platform status', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchStatus(); }, [token]);

  const handleLogin = async () => {
    if (!loginDialog || !token) return;
    setLoginLoading(true);
    setLoginError('');
    try {
      await API.platformLogin(loginDialog, loginForm, token);
      setLoginDialog(null);
      setLoginForm({ username: '', password: '' });
      await fetchStatus();
    } catch (e: any) {
      setLoginError(e.message || t('Login failed', '登录失败'));
    } finally {
      setLoginLoading(false);
    }
  };

  const handleLogout = async (platform: string) => {
    if (!token) return;
    try {
      await API.platformLogout(platform, token);
      await fetchStatus();
    } catch (e) {
      console.error('Logout failed', e);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, p: 3, height: '100%' }}>
      <Typography variant="h5" sx={{ color: 'text.secondary' }}>
        {t('Cross-Platform Play', '跨平台对弈')}
      </Typography>
      <Typography variant="body2" sx={{ color: 'text.secondary' }}>
        {t('Connect to Go platforms and play through your smart board', '连接围棋平台，通过智能棋盘对弈')}
      </Typography>

      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', flex: 1 }}>
        {platforms.map((p) => {
          const meta = PLATFORM_META[p.platform] || { label: p.platform, labelCn: p.platform, color: '#888' };
          return (
            <Box
              key={p.platform}
              sx={{
                flex: '1 1 calc(50% - 8px)',
                minWidth: 200,
                minHeight: 140,
                borderRadius: 3,
                bgcolor: 'background.paper',
                border: '1px solid',
                borderColor: p.connected ? 'success.main' : 'divider',
                p: 2.5,
                display: 'flex',
                flexDirection: 'column',
                gap: 1.5,
              }}
            >
              {/* Header */}
              <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: p.connected ? 'success.main' : 'text.disabled' }} />
                  <Typography variant="h6" sx={{ color: 'text.primary' }}>
                    {t(meta.label, meta.labelCn)}
                  </Typography>
                </Box>
                {p.connected && (
                  <Chip label={p.saved_username} size="small" color="success" variant="outlined" />
                )}
              </Box>

              {/* Capabilities */}
              <Box sx={{ display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                {p.supports_live_play && <Chip label={t('Live Play', '实时对弈')} size="small" variant="outlined" />}
                {p.supports_automatch && <Chip label={t('Automatch', '自动匹配')} size="small" variant="outlined" />}
                {p.supports_rooms && <Chip label={t('Rooms', '房间')} size="small" variant="outlined" />}
                {meta.comingSoon && <Chip label={t('Coming Soon', '即将支持')} size="small" color="warning" variant="outlined" />}
              </Box>

              {/* Actions */}
              <Box sx={{ display: 'flex', gap: 1, mt: 'auto' }}>
                {meta.comingSoon ? (
                  <Button variant="outlined" size="small" disabled sx={{ flex: 1, minHeight: 44, opacity: 0.5 }}>
                    {t('Coming Soon', '即将支持')}
                  </Button>
                ) : p.connected ? (
                  <>
                    <Button
                      variant="contained"
                      size="small"
                      sx={{ flex: 1, minHeight: 44 }}
                      onClick={() => navigate(`/kiosk/play/cross-platform/lobby?platform=${p.platform}`)}
                    >
                      {t('Enter Lobby', '进入大厅')}
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      color="error"
                      sx={{ minHeight: 44, minWidth: 44 }}
                      onClick={() => handleLogout(p.platform)}
                    >
                      <Logout fontSize="small" />
                    </Button>
                  </>
                ) : (
                  <Button
                    variant="outlined"
                    size="small"
                    sx={{ flex: 1, minHeight: 44 }}
                    startIcon={<Login />}
                    onClick={() => {
                      setLoginDialog(p.platform);
                      setLoginForm({ username: p.saved_username || '', password: '' });
                      setLoginError('');
                    }}
                  >
                    {t('Login', '登录')}
                  </Button>
                )}
              </Box>
            </Box>
          );
        })}
      </Box>

      {/* Login Dialog */}
      <Dialog open={!!loginDialog} onClose={() => setLoginDialog(null)} maxWidth="xs" fullWidth>
        <DialogTitle>
          {loginDialog && t(
            `Login to ${PLATFORM_META[loginDialog]?.label}`,
            `登录 ${PLATFORM_META[loginDialog]?.labelCn}`
          )}
        </DialogTitle>
        <DialogContent sx={{ display: 'flex', flexDirection: 'column', gap: 2, pt: 1 }}>
          {(() => {
            const loginCfg = loginDialog ? PLATFORM_META[loginDialog]?.login : null;
            return (
              <>
                <TextField
                  label={t(loginCfg?.userLabel || 'Username', loginCfg?.userLabelCn || '用户名')}
                  type={loginCfg?.userType || 'text'}
                  value={loginForm.username}
                  onChange={(e) => setLoginForm({ ...loginForm, username: e.target.value })}
                  fullWidth
                  autoFocus
                />
                <TextField
                  label={t(loginCfg?.passLabel || 'Password', loginCfg?.passLabelCn || '密码')}
                  type={loginCfg?.passLabel === 'Verification Code' ? 'text' : 'password'}
                  value={loginForm.password}
                  onChange={(e) => setLoginForm({ ...loginForm, password: e.target.value })}
                  fullWidth
                  onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
                />
              </>
            );
          })()}
          {loginError && (
            <Typography variant="body2" color="error">{loginError}</Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLoginDialog(null)}>{t('Cancel', '取消')}</Button>
          <Button onClick={handleLogin} variant="contained" disabled={loginLoading}>
            {loginLoading ? <CircularProgress size={20} /> : t('Login', '登录')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default PlatformConnectPage;
