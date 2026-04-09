import { Box, Typography } from '@mui/material';


interface PlatformBadgeProps {
  platform: string;
  connected: boolean;
  latency?: number;
}

const PLATFORM_COLORS: Record<string, string> = {
  ogs: '#4a90d9',
  fox: '#e67e22',
  golaxy: '#2ecc71',
  kgs: '#9b59b6',
};

/** Small badge showing which platform the current game is on + connection health. */
const PlatformBadge = ({ platform, connected, latency }: PlatformBadgeProps) => {
  const color = PLATFORM_COLORS[platform] || '#888';
  const healthColor = !connected ? 'error.main' : (latency && latency > 1000) ? 'warning.main' : 'success.main';
  return (
    <Box
      sx={{
        display: 'flex',
        alignItems: 'center',
        gap: 0.5,
        px: 1,
        py: 0.5,
        borderRadius: 1,
        bgcolor: 'background.paper',
        border: '1px solid',
        borderColor: color,
      }}
    >
      <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: healthColor }} />
      <Typography variant="caption" sx={{ color, fontWeight: 600, textTransform: 'uppercase' }}>
        {platform}
      </Typography>
    </Box>
  );
};

export default PlatformBadge;
