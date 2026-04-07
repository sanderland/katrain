import { useEffect, useRef, useState } from 'react';
import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Tooltip from '@mui/material/Tooltip';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PauseIcon from '@mui/icons-material/Pause';
import VolumeOffIcon from '@mui/icons-material/VolumeOff';

interface AudioPlayerProps {
  src: string | null;
  autoPlay?: boolean;
  onEnded?: () => void;
}

export default function AudioPlayer({ src, autoPlay = false, onEnded }: AudioPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.load();
    setPlaying(false);
    setError(false);
    if (autoPlay && src) {
      audio.play().then(() => setPlaying(true)).catch(() => { setError(true); });
    }
  }, [src, autoPlay]);

  const toggle = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
      setPlaying(false);
    } else {
      audio.play().then(() => setPlaying(true)).catch(() => { setError(true); });
    }
  };

  if (!src) return null;

  return (
    <Box display="flex" alignItems="center" gap={1}>
      <audio
        ref={audioRef}
        src={src}
        onEnded={() => { setPlaying(false); onEnded?.(); }}
        onPause={() => setPlaying(false)}
        onPlay={() => setPlaying(true)}
      />
      <IconButton onClick={toggle} size="small" color={error ? 'default' : 'primary'} aria-label={playing ? 'Pause' : 'Play'} disabled={error}>
        {playing ? <PauseIcon /> : <PlayArrowIcon />}
      </IconButton>
      {error && (
        <Tooltip title="Audio unavailable">
          <VolumeOffIcon fontSize="small" color="disabled" />
        </Tooltip>
      )}
    </Box>
  );
}
