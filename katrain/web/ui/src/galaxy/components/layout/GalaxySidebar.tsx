import { useState } from 'react';
import { Box, List, ListItemButton, ListItemIcon, ListItemText, Typography, Avatar, Divider, Button, Menu, MenuItem } from '@mui/material';
import { useLocation } from 'react-router-dom';
import SportsEsportsIcon from '@mui/icons-material/SportsEsports';
import ScienceIcon from '@mui/icons-material/Science';
import AssessmentIcon from '@mui/icons-material/Assessment'; // Report
import LiveTvIcon from '@mui/icons-material/LiveTv'; // Live
import SettingsIcon from '@mui/icons-material/Settings';
import LogoutIcon from '@mui/icons-material/Logout';
import LoginIcon from '@mui/icons-material/Login';
import LanguageIcon from '@mui/icons-material/Language';
import ExtensionIcon from '@mui/icons-material/Extension';
import LibraryBooksIcon from '@mui/icons-material/LibraryBooks';
import MenuBookIcon from '@mui/icons-material/MenuBook';
import { useAuth } from '../../../context/AuthContext';
import { useSettings } from '../../../context/SettingsContext';
import { useTranslation } from '../../../hooks/useTranslation';
import { useGameNavigation } from '../../context/GameNavigationContext';
import LoginModal from '../auth/LoginModal';

const GalaxySidebar = () => {
  const { requestNavigation } = useGameNavigation();
  const location = useLocation();
  const { user, logout } = useAuth();
  const { language, setLanguage, languages } = useSettings();
  const { t } = useTranslation();
  const [loginOpen, setLoginOpen] = useState(false);
  const [settingsAnchorEl, setSettingsAnchorEl] = useState<null | HTMLElement>(null);

  const handleLogout = async () => {
    await logout();
    // Navigate to home after logout
    requestNavigation('/galaxy');
  };

  const handleSettingsClick = (event: React.MouseEvent<HTMLElement>) => {
    setSettingsAnchorEl(event.currentTarget);
  };

  const handleSettingsClose = () => {
    setSettingsAnchorEl(null);
  };

  const handleLanguageSelect = (code: string) => {
    setLanguage(code);
    handleSettingsClose();
  };

  const menuItems = [
    { text: t('btn:Play', 'Play'), icon: <SportsEsportsIcon />, path: '/galaxy/play', disabled: false },
    { text: t('Research', 'Research'), icon: <ScienceIcon />, path: '/galaxy/research', disabled: false },
    { text: t('Tsumego', '死活题'), icon: <ExtensionIcon />, path: '/galaxy/tsumego', disabled: false },
    { text: t('analysis:report', 'Report'), icon: <AssessmentIcon />, path: '/galaxy/report', disabled: true },
    { text: t('Live', 'Live'), icon: <LiveTvIcon />, path: '/galaxy/live', disabled: false },
    { text: t('kifu:library', '棋谱库'), icon: <LibraryBooksIcon />, path: '/galaxy/kifu', disabled: false },
    { text: t('Tutorials', '教程'), icon: <MenuBookIcon />, path: '/galaxy/tutorials', disabled: false },
  ];

  return (
    <Box sx={{
      width: 240,
      minWidth: 240,
      flexShrink: 0,
      height: '100vh',
      bgcolor: 'background.paper',
      borderRight: '1px solid rgba(255,255,255,0.05)',
      display: 'flex',
      flexDirection: 'column'
    }}>
      {/* Logo Area */}
      <Box sx={{ p: 3, display: 'flex', alignItems: 'center', gap: 2, cursor: 'pointer' }} onClick={() => requestNavigation('/galaxy')}>
         <img src="/assets/img/logo-white.png" alt="弈航" style={{ width: 32, height: 32 }} />
         <Box>
           <Typography variant="h6" fontWeight="bold" sx={{ lineHeight: 1.2 }}>弈航</Typography>
           <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.65rem' }}>棋道导航者</Typography>
         </Box>
      </Box>

      <Divider sx={{ mb: 2 }} />

      {/* Navigation */}
      <List component="nav" sx={{ flexGrow: 1 }}>
        {menuItems.map((item) => {
          const isActive = location.pathname.startsWith(item.path);
          return (
            <ListItemButton
              key={item.text}
              onClick={() => !item.disabled && requestNavigation(item.path)}
              disabled={item.disabled}
              selected={isActive}
              sx={{
                mx: 1,
                borderRadius: 2,
                '&.Mui-selected': {
                    bgcolor: 'primary.dark',
                    '&:hover': { bgcolor: 'primary.dark' }
                }
              }}
            >
              <ListItemIcon sx={{ minWidth: 40, color: isActive ? 'primary.main' : 'text.secondary' }}>
                {item.icon}
              </ListItemIcon>
              <ListItemText 
                primary={item.text} 
                primaryTypographyProps={{ 
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? 'text.primary' : 'text.secondary'
                }} 
              />
            </ListItemButton>
          );
        })}
      </List>

      <Divider sx={{ mt: 2 }} />

      {/* Bottom Area: Settings & User */}
      <Box sx={{ p: 2 }}>
        <ListItemButton 
          sx={{ borderRadius: 2, mb: 1 }}
          onClick={handleSettingsClick}
        >
            <ListItemIcon sx={{ minWidth: 40 }}><SettingsIcon /></ListItemIcon>
            <ListItemText primary={t('Settings', 'Settings')} />
        </ListItemButton>

        <Menu
          anchorEl={settingsAnchorEl}
          open={Boolean(settingsAnchorEl)}
          onClose={handleSettingsClose}
          anchorOrigin={{
            vertical: 'top',
            horizontal: 'right',
          }}
          transformOrigin={{
            vertical: 'bottom',
            horizontal: 'left',
          }}
          sx={{ mb: 2 }}
        >
          <Box sx={{ px: 2, py: 1 }}>
            <Typography variant="overline" color="text.secondary">{t('Language', 'Language')}</Typography>
          </Box>
          {languages.map((lang) => (
            <MenuItem 
              key={lang.code} 
              onClick={() => handleLanguageSelect(lang.code)}
              selected={language === lang.code}
              sx={{ minWidth: 160, display: 'flex', gap: 1 }}
            >
              <LanguageIcon fontSize="small" sx={{ color: 'text.secondary' }} />
              <ListItemText primary={lang.name} />
            </MenuItem>
          ))}
        </Menu>

        {user ? (
            <Box sx={{ p: 1.5, bgcolor: 'background.default', borderRadius: 2, display: 'flex', alignItems: 'center', gap: 1.5 }}>
                <Avatar sx={{ width: 32, height: 32, bgcolor: 'primary.main', fontSize: '0.75rem' }}>
                    {user.rank === '20k' ? '?' : user.rank}
                </Avatar>
                <Box sx={{ flexGrow: 1, minWidth: 0, overflow: 'hidden' }}>
                    <Typography variant="subtitle2" noWrap>{user.username}</Typography>
                    <Typography variant="caption" color="primary.main" sx={{ fontWeight: 600 }}>
                        {user.rank === '20k' ? t('No Rank', 'No Rank') : user.rank}
                    </Typography>
                </Box>
                <LogoutIcon fontSize="small" sx={{ color: 'text.secondary', cursor: 'pointer' }} onClick={handleLogout} />
            </Box>
        ) : (
            <Button 
                variant="outlined" 
                fullWidth 
                startIcon={<LoginIcon />}
                onClick={() => setLoginOpen(true)}
            >
                {t('Login', 'Sign In')}
            </Button>
        )}
      </Box>
      <LoginModal open={loginOpen} onClose={() => setLoginOpen(false)} />
    </Box>
  );
};

export default GalaxySidebar;