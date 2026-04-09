import { Box, Typography, ButtonBase } from '@mui/material';
import { useNavigate } from 'react-router-dom';

interface ModeCardProps {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  to: string;
  compact?: boolean;
}

const ModeCard = ({ title, subtitle, icon, to, compact }: ModeCardProps) => {
  const navigate = useNavigate();

  return (
    <ButtonBase
      onClick={() => navigate(to)}
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: compact ? 1 : 2,
        flex: 1,
        minHeight: compact ? 140 : 200,
        borderRadius: 3,
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: 'divider',
        p: compact ? 2 : 3,
        transition: 'transform 100ms ease-out, border-color 200ms',
        '&:active': {
          transform: 'scale(0.96)',
          borderColor: 'primary.main',
        },
      }}
    >
      <Box sx={{ fontSize: compact ? 36 : 48, color: 'primary.main', display: 'flex' }}>{icon}</Box>
      <Typography variant={compact ? "h5" : "h4"} sx={{ color: 'text.primary' }}>{title}</Typography>
      <Typography variant="body2" sx={{ color: 'text.secondary', textAlign: 'center' }}>
        {subtitle}
      </Typography>
    </ButtonBase>
  );
};

export default ModeCard;
