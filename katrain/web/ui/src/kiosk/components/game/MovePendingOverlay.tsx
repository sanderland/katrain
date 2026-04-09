import { Box, Typography } from '@mui/material';
import { HourglassTop } from '@mui/icons-material';

interface MovePendingOverlayProps {
  col: number;
  row: number;
}

/** Pulsing overlay shown while waiting for platform to ACK a move. */
const MovePendingOverlay = (_props: MovePendingOverlayProps) => (
  <Box
    sx={{
      position: 'absolute',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      bgcolor: 'rgba(0,0,0,0.5)',
      zIndex: 100,
      pointerEvents: 'all',
      animation: 'fadeIn 150ms ease-out',
      '@keyframes fadeIn': {
        from: { opacity: 0 },
        to: { opacity: 1 },
      },
    }}
  >
    <HourglassTop
      sx={{
        fontSize: 48,
        color: 'warning.main',
        animation: 'spin 1.5s linear infinite',
        '@keyframes spin': {
          from: { transform: 'rotate(0deg)' },
          to: { transform: 'rotate(360deg)' },
        },
      }}
    />
    <Typography variant="h6" sx={{ color: 'warning.main', mt: 1 }}>
      确认中...
    </Typography>
  </Box>
);

export default MovePendingOverlay;
