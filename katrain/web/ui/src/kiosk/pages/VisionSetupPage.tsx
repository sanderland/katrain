import { useState, useCallback, useEffect, useRef } from 'react';
import { Box, Button, Typography, Paper } from '@mui/material';
import { useNavigate } from 'react-router-dom';
import { Videocam, VideocamOff, ArrowBack, Check, Refresh } from '@mui/icons-material';
import { useVision } from '../context/VisionContext';
import { API } from '../../api';
import VisionBoard from '../components/vision/VisionBoard';

const STREAM_URL = '/api/v1/vision/stream';
const BOARD_POLL_MS = 500;

const VisionSetupPage = () => {
  const navigate = useNavigate();
  const { visionStatus, refreshStatus } = useVision();

  const [streamError, setStreamError] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [streamKey, setStreamKey] = useState(0);
  const [detectedBoard, setDetectedBoard] = useState<number[][] | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll detected board state
  useEffect(() => {
    const poll = async () => {
      try {
        const resp = await fetch('/api/v1/vision/detected-board');
        const data = await resp.json();
        setDetectedBoard(data.board);
      } catch {
        // ignore fetch errors
      }
    };
    poll(); // immediate first fetch
    pollRef.current = setInterval(poll, BOARD_POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleStreamError = useCallback(() => {
    setStreamError(true);
  }, []);

  const handleRetry = useCallback(() => {
    setStreamError(false);
    setStreamKey((k) => k + 1);
  }, []);

  const handleConfirm = useCallback(async () => {
    setConfirming(true);
    try {
      await API.visionConfirmPoseLock();
      await refreshStatus();
      navigate(-1);
    } catch (err) {
      console.error('Pose lock confirmation failed', err);
    } finally {
      setConfirming(false);
    }
  }, [navigate, refreshStatus]);

  const handleBack = useCallback(() => {
    navigate(-1);
  }, [navigate]);

  const statusText = visionStatus.poseLocked ? '棋盘已识别' : '正在检测棋盘...';
  const statusColor = visionStatus.poseLocked ? 'success.main' : 'warning.main';

  return (
    <Box
      sx={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        width: '100%',
        overflow: 'hidden',
        bgcolor: 'background.default',
      }}
    >
      {/* Stream + Board side by side */}
      <Box
        sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 2,
          px: 2,
          pt: 2,
          pb: 1,
          overflow: 'hidden',
        }}
      >
        {/* Camera stream */}
        <Paper
          elevation={2}
          sx={{
            flex: 1,
            maxWidth: 480,
            aspectRatio: '4 / 3',
            overflow: 'hidden',
            borderRadius: 2,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: 'grey.900',
            position: 'relative',
          }}
        >
          {streamError ? (
            <Box
              sx={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 2,
              }}
            >
              <VideocamOff sx={{ fontSize: 48, color: 'error.main' }} />
              <Typography variant="body1" sx={{ color: 'error.light' }}>
                摄像头连接中断
              </Typography>
              <Button
                variant="outlined"
                color="error"
                startIcon={<Refresh />}
                onClick={handleRetry}
              >
                重试
              </Button>
            </Box>
          ) : (
            <img
              key={streamKey}
              src={STREAM_URL}
              alt="摄像头画面"
              onError={handleStreamError}
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'contain',
                display: 'block',
              }}
            />
          )}
        </Paper>

        {/* Detected electronic board */}
        <Paper
          elevation={2}
          sx={{
            flex: 1,
            maxWidth: 480,
            aspectRatio: '1 / 1',
            overflow: 'hidden',
            borderRadius: 2,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            bgcolor: 'grey.900',
          }}
        >
          <VisionBoard board={detectedBoard} />
        </Paper>
      </Box>

      {/* Status + actions */}
      <Box
        sx={{
          px: 2,
          pb: 2,
          pt: 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 1.5,
          flexShrink: 0,
        }}
      >
        {/* Status indicator */}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Box
            sx={{
              width: 10,
              height: 10,
              borderRadius: '50%',
              bgcolor: statusColor,
            }}
          />
          <Typography variant="body1" sx={{ color: 'text.primary' }}>
            {statusText}
          </Typography>
          {visionStatus.cameraConnected ? (
            <Videocam sx={{ fontSize: 20, color: 'success.main', ml: 1 }} />
          ) : (
            <VideocamOff sx={{ fontSize: 20, color: 'error.main', ml: 1 }} />
          )}
        </Box>

        {/* Action buttons */}
        <Box sx={{ display: 'flex', gap: 2, width: '100%', maxWidth: 400 }}>
          <Button
            variant="outlined"
            size="large"
            startIcon={<ArrowBack />}
            onClick={handleBack}
            sx={{ flex: 1, minHeight: 48 }}
          >
            返回
          </Button>
          <Button
            variant="contained"
            size="large"
            startIcon={<Check />}
            onClick={handleConfirm}
            disabled={confirming || !visionStatus.poseLocked}
            sx={{ flex: 1, minHeight: 48 }}
          >
            {confirming ? '确认中...' : '确认'}
          </Button>
        </Box>
      </Box>
    </Box>
  );
};

export default VisionSetupPage;
