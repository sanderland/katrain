import { Box, Typography } from '@mui/material';
import type { PlatformClockState } from '../../../api';

interface PlatformTimerProps {
  clock: PlatformClockState | null;
  myColor: 'B' | 'W';
}

function formatTime(seconds: number): string {
  if (seconds < 0) seconds = 0;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

function parseThinkingTime(time: any): number {
  if (typeof time === 'number') return time;
  if (typeof time === 'object' && time !== null) return time.thinking_time || 0;
  return 0;
}

function parsePeriods(time: any): { periods: number; periodTime: number } | null {
  if (typeof time !== 'object' || !time) return null;
  if (time.periods !== undefined) return { periods: time.periods, periodTime: time.period_time || 30 };
  return null;
}

const TimerSide = ({ label, time, isActive, isLow }: {
  label: string;
  time: any;
  isActive: boolean;
  isLow: boolean;
}) => {
  const thinkingTime = parseThinkingTime(time);
  const periods = parsePeriods(time);

  return (
    <Box sx={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 0.5,
      p: 1.5,
      borderRadius: 2,
      bgcolor: isActive ? 'rgba(92,181,122,0.15)' : 'transparent',
      border: '1px solid',
      borderColor: isActive ? 'primary.main' : 'divider',
      minWidth: 100,
    }}>
      <Typography variant="caption" sx={{ color: 'text.secondary', textTransform: 'uppercase', letterSpacing: 1 }}>
        {label}
      </Typography>
      <Typography
        variant="h5"
        sx={{
          fontFamily: 'JetBrains Mono, monospace',
          color: isLow ? 'error.main' : 'text.primary',
          animation: isLow && isActive ? 'pulse 1s infinite' : 'none',
          '@keyframes pulse': {
            '0%, 100%': { opacity: 1 },
            '50%': { opacity: 0.5 },
          },
        }}
      >
        {formatTime(thinkingTime)}
      </Typography>
      {periods && (
        <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
          {Array.from({ length: periods.periods }, (_, i) => (
            <Box
              key={i}
              sx={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                bgcolor: 'primary.main',
              }}
            />
          ))}
          <Typography variant="caption" sx={{ color: 'text.secondary', ml: 0.5 }}>
            {periods.periodTime}s
          </Typography>
        </Box>
      )}
    </Box>
  );
};

const PlatformTimer = ({ clock }: PlatformTimerProps) => {
  if (!clock) return null;

  const blackTime = parseThinkingTime(clock.black_time);
  const whiteTime = parseThinkingTime(clock.white_time);

  return (
    <Box sx={{ display: 'flex', gap: 1.5, justifyContent: 'center' }}>
      <TimerSide
        label="Black"
        time={clock.black_time}
        isActive={clock.current_player === 'B'}
        isLow={blackTime < 30}
      />
      <TimerSide
        label="White"
        time={clock.white_time}
        isActive={clock.current_player === 'W'}
        isLow={whiteTime < 30}
      />
    </Box>
  );
};

export default PlatformTimer;
