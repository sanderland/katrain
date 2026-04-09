import { useEffect, useState, useCallback } from 'react';
import {
  Box, Typography, Button, List, ListItem, ListItemText,
  Chip, CircularProgress, TextField, Tab, Tabs, Dialog,
  DialogTitle, DialogContent, DialogActions, Snackbar, Alert,
} from '@mui/material';
import { Search, SportsKabaddi, Casino } from '@mui/icons-material';
import { useSearchParams } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useTranslation } from '../../hooks/useTranslation';
import { API, type PlatformUser, type PlatformInfo } from '../../api';

const PlatformLobbyPage = () => {
  const { t } = useTranslation();
  const { token } = useAuth();
  const [searchParams] = useSearchParams();
  const initialPlatform = searchParams.get('platform') || 'ogs';

  const [platforms, setPlatforms] = useState<PlatformInfo[]>([]);
  const [activePlatform, setActivePlatform] = useState(initialPlatform);
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [automatchActive, setAutomatchActive] = useState(false);
  const [challengeTarget, setChallengeTarget] = useState<PlatformUser | null>(null);
  const [toast, setToast] = useState<{ message: string; severity: 'success' | 'error' } | null>(null);

  const fetchPlatforms = async () => {
    if (!token) return;
    try {
      const data = await API.platformStatus(token);
      setPlatforms(data.platforms.filter(p => p.connected));
    } catch (e) {
      console.error('Failed to fetch platforms', e);
    }
  };

  const fetchUsers = useCallback(async (query?: string) => {
    if (!token) return;
    setLoading(true);
    try {
      const data = await API.platformUsers(activePlatform, token, query || undefined);
      setUsers(data.users);
    } catch (e) {
      console.error('Failed to fetch users', e);
      setUsers([]);
    } finally {
      setLoading(false);
    }
  }, [activePlatform, token]);

  useEffect(() => { fetchPlatforms(); }, [token]);
  useEffect(() => { fetchUsers(); }, [fetchUsers]);

  // Debounced search: fetch from server when user types
  useEffect(() => {
    if (!searchQuery) { fetchUsers(); return; }
    const timer = setTimeout(() => fetchUsers(searchQuery), 400);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleChallenge = async (user: PlatformUser) => {
    if (!token) return;
    try {
      await API.platformSendChallenge(activePlatform, {
        user_id: user.user_id,
        board_size: 19,
        rules: 'chinese',
        ranked: true,
      }, token);
      setToast({ message: t('Challenge sent!', '已发起挑战！'), severity: 'success' });
      setChallengeTarget(null);
    } catch (e: any) {
      setToast({ message: e.message || t('Challenge failed', '挑战失败'), severity: 'error' });
    }
  };

  const toggleAutomatch = async () => {
    if (!token) return;
    try {
      if (automatchActive) {
        await API.platformCancelAutomatch(activePlatform, token);
        setAutomatchActive(false);
      } else {
        await API.platformStartAutomatch(activePlatform, { board_size: 19 }, token);
        setAutomatchActive(true);
      }
    } catch (e: any) {
      setToast({ message: e.message, severity: 'error' });
    }
  };

  const connectedPlatforms = platforms.filter(p => p.connected);
  const currentPlatform = connectedPlatforms.find(p => p.platform === activePlatform);
  const filteredUsers = users; // Filtering now done server-side

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%', p: 2, gap: 1.5 }}>
      {/* Platform tabs */}
      {connectedPlatforms.length > 1 && (
        <Tabs
          value={activePlatform}
          onChange={(_, v) => setActivePlatform(v)}
          variant="scrollable"
          sx={{ minHeight: 44 }}
        >
          {connectedPlatforms.map(p => (
            <Tab key={p.platform} value={p.platform} label={p.platform.toUpperCase()} sx={{ minHeight: 44 }} />
          ))}
        </Tabs>
      )}

      {/* Search + automatch bar */}
      <Box sx={{ display: 'flex', gap: 1, alignItems: 'center' }}>
        <TextField
          size="small"
          placeholder={t('Search players...', '搜索玩家...')}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          sx={{ flex: 1 }}
          InputProps={{ startAdornment: <Search sx={{ color: 'text.secondary', mr: 0.5 }} /> }}
        />
        {currentPlatform?.supports_automatch && (
          <Button
            variant={automatchActive ? "contained" : "outlined"}
            color={automatchActive ? "warning" : "primary"}
            startIcon={<Casino />}
            onClick={toggleAutomatch}
            sx={{ minHeight: 44, whiteSpace: 'nowrap' }}
          >
            {automatchActive ? t('Cancel Match', '取消匹配') : t('Automatch', '自动匹配')}
          </Button>
        )}
      </Box>

      {/* User list */}
      <Box sx={{ flex: 1, overflow: 'auto', borderRadius: 2, bgcolor: 'background.paper', border: '1px solid', borderColor: 'divider' }}>
        {loading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
            <CircularProgress />
          </Box>
        ) : filteredUsers.length === 0 ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, p: 4 }}>
            {searchQuery ? (
              <Typography color="text.secondary">
                {t('No players found', '未找到匹配的棋手')}
              </Typography>
            ) : (
              <>
                <Typography color="text.secondary" sx={{ textAlign: 'center' }}>
                  {t(
                    'Search for a player by username to send a challenge, or use Automatch to find a game automatically.',
                    '在搜索框中输入用户名查找棋手并发起挑战，或点击「自动匹配」快速开始对局。'
                  )}
                </Typography>
              </>
            )}
          </Box>
        ) : (
          <List disablePadding>
            {filteredUsers.map((user) => (
              <ListItem
                key={user.user_id}
                sx={{ borderBottom: '1px solid', borderColor: 'divider', minHeight: 48 }}
                secondaryAction={
                  <Button
                    variant="outlined"
                    size="small"
                    startIcon={<SportsKabaddi />}
                    onClick={() => setChallengeTarget(user)}
                    disabled={user.status === 'playing'}
                    sx={{ minHeight: 44, minWidth: 44 }}
                  >
                    {t('Challenge', '挑战')}
                  </Button>
                }
              >
                <ListItemText
                  primary={
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Typography>{user.username}</Typography>
                      <Chip label={user.rank} size="small" variant="outlined" />
                    </Box>
                  }
                  secondary={user.status === 'playing' ? t('In game', '对局中') : user.status === 'seeking' ? t('Seeking game', '寻找对手中') : t('Idle', '空闲')}
                />
              </ListItem>
            ))}
          </List>
        )}
      </Box>

      {/* Challenge confirmation dialog */}
      <Dialog open={!!challengeTarget} onClose={() => setChallengeTarget(null)} maxWidth="xs" fullWidth>
        <DialogTitle>
          {t('Send Challenge', '发起挑战')}
        </DialogTitle>
        <DialogContent>
          <Typography>
            {challengeTarget && t(
              `Challenge ${challengeTarget.username} (${challengeTarget.rank})?`,
              `向 ${challengeTarget.username} (${challengeTarget.rank}) 发起挑战？`
            )}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setChallengeTarget(null)}>{t('Cancel', '取消')}</Button>
          <Button variant="contained" onClick={() => challengeTarget && handleChallenge(challengeTarget)}>
            {t('Send', '发送')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Toast */}
      {toast && (
        <Snackbar open autoHideDuration={3000} onClose={() => setToast(null)}>
          <Alert severity={toast.severity} onClose={() => setToast(null)}>{toast.message}</Alert>
        </Snackbar>
      )}
    </Box>
  );
};

export default PlatformLobbyPage;
