import { Box, Typography } from '@mui/material';
import { SportsEsports, EmojiEvents, Handshake, Public, Language } from '@mui/icons-material';
import ModeCard from '../components/common/ModeCard';
import { useTranslation } from '../../hooks/useTranslation';

const PlayPage = () => {
  const { t } = useTranslation();
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, p: 3, height: '100%', overflow: 'auto' }}>
      <Typography variant="h5" sx={{ color: 'text.secondary' }}>{t('Play vs AI', '人机对弈')}</Typography>
      <Box sx={{ display: 'flex', gap: 2, flex: 1 }}>
        <ModeCard
          title={t('Free Game', '自由对弈')}
          subtitle={t('Choose AI strength and board settings freely', '随意选择AI强度和棋盘设置')}
          icon={<SportsEsports fontSize="inherit" />}
          to="/kiosk/play/ai/setup/free"
          compact
        />
        <ModeCard
          title={t('Ranked Game', '升降级对弈')}
          subtitle={t('Auto-match AI difficulty based on your skill', '根据实力自动匹配AI难度')}
          icon={<EmojiEvents fontSize="inherit" />}
          to="/kiosk/play/ai/setup/ranked"
          compact
        />
      </Box>
      <Typography variant="h5" sx={{ color: 'text.secondary' }}>{t('Play vs Human', '人人对弈')}</Typography>
      <Box sx={{ display: 'flex', gap: 2, flex: 1 }}>
        <ModeCard
          title={t('Local Game', '本地对局')}
          subtitle={t('Play face-to-face on the smart board', '两人在智能棋盘上面对面对弈')}
          icon={<Handshake fontSize="inherit" />}
          to="/kiosk/play/pvp/setup"
          compact
        />
        <ModeCard
          title={t('Online Lobby', '在线大厅')}
          subtitle={t('Match with online opponents', '匹配网络上的对手进行对弈')}
          icon={<Public fontSize="inherit" />}
          to="/kiosk/play/pvp/lobby"
          compact
        />
        <ModeCard
          title={t('Cross-Platform', '跨平台对弈')}
          subtitle={t('Play on OGS, Fox, and more', '连接 OGS、野狐等平台')}
          icon={<Language fontSize="inherit" />}
          to="/kiosk/play/cross-platform"
          compact
        />
      </Box>
    </Box>
  );
};

export default PlayPage;
