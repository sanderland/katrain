import { useState, useRef, useCallback } from 'react';
import type { BoardPayload, EditTool, StoneEditMode, ShapeType } from '../../types/tutorial';

const MAX_UNDO = 50;

function emptyPayload(): BoardPayload {
  return { size: 19, stones: { B: [], W: [] }, labels: {}, letters: {}, shapes: {}, highlights: [] };
}

export interface BoardEditorState {
  payload: BoardPayload;
  savedPayload: BoardPayload;
  isEditing: boolean;
  activeTool: EditTool;
  stoneMode: StoneEditMode;
  nextStoneColor: 'B' | 'W';
  numbering: boolean;
  nextMoveNumber: number;
  selectedShape: ShapeType;
  canUndo: boolean;

  enterEdit: () => void;
  cancelEdit: () => void;
  save: () => Promise<void>;
  undo: () => void;
  handleClick: (col: number, row: number) => void;
  setActiveTool: (tool: EditTool) => void;
  setStoneMode: (mode: StoneEditMode) => void;
  setNumbering: (v: boolean) => void;
  setNextMoveNumber: (n: number) => void;
  setSelectedShape: (s: ShapeType) => void;
  setPayloadFromServer: (p: BoardPayload) => void;
}

export function useBoardEditor(
  initialPayload: BoardPayload | null,
  onSave: (payload: BoardPayload) => Promise<void>,
): BoardEditorState {
  const [payload, setPayload] = useState<BoardPayload>(initialPayload ?? emptyPayload());
  const [savedPayload, setSavedPayload] = useState<BoardPayload>(initialPayload ?? emptyPayload());
  const [undoStack, setUndoStack] = useState<BoardPayload[]>([]);
  const [isEditing, setIsEditing] = useState(false);
  const [activeTool, setActiveToolState] = useState<EditTool>(null);
  const [stoneMode, setStoneMode] = useState<StoneEditMode>('black');
  const [nextStoneColor, setNextStoneColor] = useState<'B' | 'W'>('B');
  const [numbering, setNumbering] = useState(false);
  const [selectedShape, setSelectedShape] = useState<ShapeType>('triangle');

  const [moveCounter, setMoveCounter] = useState(0);
  const letterCounterRef = useRef(0);

  const computeMaxLabel = (p: BoardPayload): number => {
    let max = 0;
    for (const val of Object.values(p.labels ?? {})) {
      const n = parseInt(val, 10);
      if (!isNaN(n) && n > max) max = n;
    }
    return max;
  };

  const computeMaxLetter = (p: BoardPayload): number => {
    let max = -1;
    for (const val of Object.values(p.letters ?? {})) {
      const code = val.charCodeAt(0) - 65; // A=0, B=1, ...
      if (code > max) max = code;
    }
    return max + 1; // next letter index
  };

  const enterEdit = useCallback(() => {
    setMoveCounter(computeMaxLabel(payload));
    letterCounterRef.current = computeMaxLetter(payload);
    setUndoStack([]);
    setIsEditing(true);
    setActiveToolState('stone');
    // Determine next stone color from existing stones
    const bCount = payload.stones.B.length;
    const wCount = payload.stones.W.length;
    setNextStoneColor(bCount <= wCount ? 'B' : 'W');
  }, [payload]);

  const cancelEdit = useCallback(() => {
    setPayload(savedPayload);
    setIsEditing(false);
    setActiveToolState(null);
  }, [savedPayload]);

  const save = useCallback(async () => {
    await onSave(payload);
    setSavedPayload(payload);
    setIsEditing(false);
    setActiveToolState(null);
  }, [payload, onSave]);

  const undo = useCallback(() => {
    setUndoStack(stack => {
      if (stack.length === 0) return stack;
      const prev = stack[stack.length - 1];
      setPayload(prev);
      // Recompute counters from restored state
      setMoveCounter(computeMaxLabel(prev));
      letterCounterRef.current = computeMaxLetter(prev);
      return stack.slice(0, -1);
    });
  }, []);

  const setActiveTool = useCallback((tool: EditTool) => {
    setActiveToolState(tool);
    if (tool === 'letter') {
      // Rescan current payload for max letter
      setPayload(p => {
        letterCounterRef.current = computeMaxLetter(p);
        return p;
      });
    }
  }, []);

  const setPayloadFromServer = useCallback((p: BoardPayload) => {
    setPayload(p);
    setSavedPayload(p);
  }, []);

  const handleClick = useCallback((col: number, row: number) => {
    if (!isEditing || !activeTool) return;

    setPayload(prev => {
      const coordKey = `${col},${row}`;
      const hasStone = prev.stones.B.some(([c, r]) => c === col && r === row) ||
                       prev.stones.W.some(([c, r]) => c === col && r === row);
      const hasLetter = !!(prev.letters ?? {})[coordKey];
      const hasShape = !!(prev.shapes ?? {})[coordKey];

      // Push undo before mutation
      setUndoStack(stack => [...stack.slice(-(MAX_UNDO - 1)), prev]);
      const next = structuredClone(prev);

      if (activeTool === 'eraser') {
        // Remove everything at position
        next.stones.B = next.stones.B.filter(([c, r]) => c !== col || r !== row);
        next.stones.W = next.stones.W.filter(([c, r]) => c !== col || r !== row);
        if (next.labels) delete next.labels[coordKey];
        if (next.letters) delete next.letters[coordKey];
        if (next.shapes) delete next.shapes[coordKey];
        next.highlights = (next.highlights ?? []).filter(([c, r]) => c !== col || r !== row);
        return next;
      }

      if (activeTool === 'stone') {
        if (hasStone || hasLetter || hasShape) return prev; // blocked
        const color = stoneMode === 'alternate' ? nextStoneColor : (stoneMode === 'black' ? 'B' : 'W');
        next.stones[color].push([col, row]);
        if (numbering) {
          const num = moveCounter + 1;
          setMoveCounter(num);
          if (!next.labels) next.labels = {};
          next.labels[coordKey] = String(num);
        }
        if (stoneMode === 'alternate') {
          setNextStoneColor(color === 'B' ? 'W' : 'B');
        }
        return next;
      }

      if (activeTool === 'letter') {
        if (hasStone || hasShape) return prev; // blocked by different type
        if (letterCounterRef.current > 25) {
          alert('字母已用完 (A-Z)');
          return prev;
        }
        const letter = String.fromCharCode(65 + letterCounterRef.current);
        if (!next.letters) next.letters = {};
        next.letters[coordKey] = letter;
        letterCounterRef.current += 1;
        return next;
      }

      if (activeTool === 'shape') {
        if (hasLetter) return prev; // blocked by letter
        // Shapes can be placed on stones (e.g. triangle on black/white stone) or empty intersections
        if (!next.shapes) next.shapes = {};
        next.shapes[coordKey] = selectedShape;
        return next;
      }

      return prev;
    });
  }, [isEditing, activeTool, stoneMode, nextStoneColor, numbering, moveCounter, selectedShape]);

  return {
    payload,
    savedPayload,
    isEditing,
    activeTool,
    stoneMode,
    nextStoneColor,
    numbering,
    nextMoveNumber: moveCounter + 1,
    selectedShape,
    canUndo: undoStack.length > 0,

    enterEdit,
    cancelEdit,
    save,
    undo,
    handleClick,
    setActiveTool,
    setStoneMode,
    setNumbering,
    setNextMoveNumber: (n: number) => setMoveCounter(n - 1),
    setSelectedShape,
    setPayloadFromServer,
  };
}
