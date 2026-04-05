import Box from '@mui/material/Box';
import IconButton from '@mui/material/IconButton';
import Button from '@mui/material/Button';
import Menu from '@mui/material/Menu';
import MenuItem from '@mui/material/MenuItem';
import TextField from '@mui/material/TextField';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import UndoIcon from '@mui/icons-material/Undo';
import SaveIcon from '@mui/icons-material/Save';
import CloseIcon from '@mui/icons-material/Close';
import { useState } from 'react';
import type { EditTool, StoneEditMode, ShapeType } from '../../../types/tutorial';

/* ── Stone icon components (matching ResearchToolbar style) ── */

function BlackStoneIcon({ size = 16 }: { size?: number }) {
  return (
    <Box sx={{
      width: size, height: size, borderRadius: '50%',
      bgcolor: '#1a1a1a', border: '1.5px solid rgba(255,255,255,0.2)',
      boxSizing: 'border-box', boxShadow: 'inset 0 -1px 2px rgba(255,255,255,0.1)',
    }} />
  );
}

function WhiteStoneIcon({ size = 16 }: { size?: number }) {
  return (
    <Box sx={{
      width: size, height: size, borderRadius: '50%',
      bgcolor: '#fff', border: '1.5px solid rgba(0,0,0,0.3)',
      boxSizing: 'border-box', boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.08)',
    }} />
  );
}

function AlternateIcon({ size = 16 }: { size?: number }) {
  const s = size * 0.8;
  const overlap = s * 0.35;
  return (
    <Box sx={{ width: s * 2 - overlap, height: s, position: 'relative' }}>
      <Box sx={{
        width: s, height: s, borderRadius: '50%', bgcolor: '#1a1a1a',
        position: 'absolute', left: 0, zIndex: 1,
        border: '1.5px solid rgba(255,255,255,0.2)', boxSizing: 'border-box',
      }} />
      <Box sx={{
        width: s, height: s, borderRadius: '50%', bgcolor: '#fff',
        position: 'absolute', left: s - overlap, zIndex: 2,
        border: '1.5px solid rgba(0,0,0,0.3)', boxSizing: 'border-box',
      }} />
    </Box>
  );
}

/* ── ToolButton (adapted from ResearchToolbar) ── */

function ToolButton({ icon, label, active, onClick, disabled, compact }: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: (e: React.MouseEvent) => void;
  disabled?: boolean;
  compact?: boolean;
}) {
  return (
    <Tooltip title={label}>
      <Box
        onClick={(e) => !disabled && onClick(e)}
        sx={{
          py: compact ? 0.5 : 0.75,
          px: compact ? 0.75 : 1,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          cursor: disabled ? 'default' : 'pointer',
          bgcolor: active ? 'rgba(74, 107, 92, 0.2)' : 'rgba(255,255,255,0.04)',
          color: active ? 'primary.light' : 'text.primary',
          opacity: disabled ? 0.3 : 1,
          border: '1px solid',
          borderColor: active ? 'primary.main' : 'rgba(255,255,255,0.06)',
          borderRadius: 1,
          transition: 'all 0.15s ease',
          minWidth: 36,
          '&:hover': {
            bgcolor: disabled ? 'rgba(255,255,255,0.04)'
              : active ? 'rgba(74, 107, 92, 0.3)' : 'rgba(255,255,255,0.08)',
          },
        }}
      >
        {icon}
        <Typography variant="caption" sx={{ mt: 0.25, fontSize: '0.65rem', lineHeight: 1.2, whiteSpace: 'nowrap' }}>
          {label}
        </Typography>
      </Box>
    </Tooltip>
  );
}

/* ── Main toolbar ── */

interface BoardEditToolbarProps {
  activeTool: EditTool;
  stoneMode: StoneEditMode;
  numbering: boolean;
  nextMoveNumber: number;
  selectedShape: ShapeType;
  canUndo: boolean;
  onToolChange: (tool: EditTool) => void;
  onStoneModeChange: (mode: StoneEditMode) => void;
  onNumberingChange: (v: boolean) => void;
  onNextMoveNumberChange: (n: number) => void;
  onShapeChange: (s: ShapeType) => void;
  onUndo: () => void;
  onSave: () => void;
  onCancel: () => void;
}

export default function BoardEditToolbar({
  activeTool, stoneMode, numbering, nextMoveNumber, selectedShape, canUndo,
  onToolChange, onStoneModeChange, onNumberingChange, onNextMoveNumberChange, onShapeChange,
  onUndo, onSave, onCancel,
}: BoardEditToolbarProps) {
  const [shapeAnchor, setShapeAnchor] = useState<null | HTMLElement>(null);

  return (
    <Box display="flex" flexWrap="wrap" gap={0.5} alignItems="center" py={0.5}>
      {/* Row 1: Tool group */}
      <Box display="flex" gap={0.25}>
        <ToolButton
          icon={<BlackStoneIcon />}
          label="摆黑"
          active={activeTool === 'stone' && stoneMode === 'black'}
          onClick={() => { onToolChange('stone'); onStoneModeChange('black'); }}
        />
        <ToolButton
          icon={<WhiteStoneIcon />}
          label="摆白"
          active={activeTool === 'stone' && stoneMode === 'white'}
          onClick={() => { onToolChange('stone'); onStoneModeChange('white'); }}
        />
        <ToolButton
          icon={<AlternateIcon />}
          label="交替"
          active={activeTool === 'stone' && stoneMode === 'alternate'}
          onClick={() => { onToolChange('stone'); onStoneModeChange('alternate'); }}
        />
      </Box>

      {/* Numbering toggle + number input */}
      {activeTool === 'stone' && (
        <Box display="flex" gap={0.25} alignItems="center">
          <ToolButton
            icon={<Typography sx={{ fontSize: 13, fontWeight: 700, lineHeight: 1 }}>123</Typography>}
            label="编号"
            active={numbering}
            onClick={() => onNumberingChange(!numbering)}
            compact
          />
          {numbering && (
            <TextField
              size="small"
              type="number"
              value={nextMoveNumber}
              onChange={e => {
                const n = parseInt(e.target.value, 10);
                if (!isNaN(n) && n > 0) onNextMoveNumberChange(n);
              }}
              inputProps={{ min: 1, style: { textAlign: 'center', padding: '4px 2px' } }}
              sx={{ width: 48, '& .MuiOutlinedInput-root': { height: 32 } }}
            />
          )}
        </Box>
      )}

      <Box sx={{ width: '1px', height: 28, bgcolor: 'divider', mx: 0.5 }} />

      {/* Annotation tools */}
      <Box display="flex" gap={0.25}>
        <ToolButton
          icon={<Typography sx={{ fontSize: 12, fontWeight: 700, lineHeight: 1 }}>ABC</Typography>}
          label="字母"
          active={activeTool === 'letter'}
          onClick={() => onToolChange('letter')}
          compact
        />
        <ToolButton
          icon={<Typography sx={{ fontSize: 14, lineHeight: 1 }}>△</Typography>}
          label="图形"
          active={activeTool === 'shape'}
          onClick={(e) => { onToolChange('shape'); setShapeAnchor(e.currentTarget as HTMLElement); }}
          compact
        />
        <ToolButton
          icon={<Typography sx={{ fontSize: 14, lineHeight: 1 }}>✕</Typography>}
          label="橡皮"
          active={activeTool === 'eraser'}
          onClick={() => onToolChange('eraser')}
          compact
        />
      </Box>

      {/* Shape submenu */}
      <Menu anchorEl={shapeAnchor} open={Boolean(shapeAnchor)} onClose={() => setShapeAnchor(null)}>
        <MenuItem selected={selectedShape === 'triangle'} onClick={() => { onShapeChange('triangle'); setShapeAnchor(null); }}>△ 三角形</MenuItem>
        <MenuItem selected={selectedShape === 'square'} onClick={() => { onShapeChange('square'); setShapeAnchor(null); }}>□ 正方形</MenuItem>
        <MenuItem selected={selectedShape === 'circle'} onClick={() => { onShapeChange('circle'); setShapeAnchor(null); }}>○ 圆形</MenuItem>
        <MenuItem selected={selectedShape === 'cross'} onClick={() => { onShapeChange('cross'); setShapeAnchor(null); }}>✕ 叉形</MenuItem>
      </Menu>

      <Box sx={{ flexGrow: 1 }} />

      {/* Actions */}
      <Tooltip title="撤销">
        <span>
          <IconButton size="small" onClick={onUndo} disabled={!canUndo}><UndoIcon /></IconButton>
        </span>
      </Tooltip>
      <Button size="small" variant="contained" startIcon={<SaveIcon />} onClick={onSave} aria-label="保存">
        保存
      </Button>
      <Button size="small" variant="outlined" startIcon={<CloseIcon />} onClick={onCancel} aria-label="取消">
        取消
      </Button>
    </Box>
  );
}
