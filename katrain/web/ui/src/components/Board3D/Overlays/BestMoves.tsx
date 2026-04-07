import { useMemo, memo } from 'react';
import { Billboard, Text } from '@react-three/drei';
import { gridToSurface, getEvalColor, EVAL_THRESHOLDS, BOARD_SURFACE_Y, STONE_HEIGHT, SURFACE_EPSILON, TEXT_FONT } from '../constants';
import type { GameState } from '../../../api';

interface BestMovesProps {
  gameState: GameState;
}

const BestMoves = ({ gameState }: BestMovesProps) => {
  const boardSize = gameState.board_size[0];
  const moves = gameState.analysis?.moves;
  const maxMoves = gameState.trainer_settings?.max_top_moves_on_board || 3;

  const topMoves = useMemo(() => {
    if (!moves) return [];
    return moves.slice(0, maxMoves).filter((m: any) => m.coords);
  }, [moves, maxMoves]);

  if (topMoves.length === 0) return null;

  return (
    <group>
      {topMoves.map((move: any, index: number) => {
        const [x, y] = move.coords;
        const surfacePos = gridToSurface(x, y, boardSize);
        const color = getEvalColor(move.scoreLoss);
        const winrateText = (move.winrate * 100).toFixed(1);
        const visitsText = move.visits >= 1000
          ? `${(move.visits / 1000).toFixed(1)}k`
          : move.visits.toString();

        // Text contrast: dark backgrounds get white text
        const evalIdx = EVAL_THRESHOLDS.findIndex(t => move.scoreLoss >= t);
        const isDarkBg = evalIdx === -1 || evalIdx <= 2 || evalIdx === 5;
        const textColor = isDarkBg ? '#ffffff' : '#000000';
        const outlineColor = isDarkBg ? '#000000' : '#ffffff';

        return (
          <group key={`best-${index}`}>
            {/* Surface circle */}
            <mesh position={surfacePos} rotation={[-Math.PI / 2, 0, 0]}>
              <circleGeometry args={[0.4, 32]} />
              <meshBasicMaterial color={color} transparent opacity={0.85} depthWrite={false} />
            </mesh>

            {/* Best move white ring */}
            {index === 0 && (
              <mesh position={[surfacePos[0], surfacePos[1] + SURFACE_EPSILON, surfacePos[2]]} rotation={[-Math.PI / 2, 0, 0]}>
                <ringGeometry args={[0.38, 0.44, 32]} />
                <meshBasicMaterial color="#ffffff" transparent opacity={0.8} depthWrite={false} />
              </mesh>
            )}

            {/* Billboard text (always faces camera) */}
            <Billboard position={[surfacePos[0], BOARD_SURFACE_Y + STONE_HEIGHT + 0.3, surfacePos[2]]}>
              <Text font={TEXT_FONT} fontSize={0.22} color={textColor} anchorX="center" anchorY="bottom" outlineWidth={0.02} outlineColor={outlineColor}>
                {winrateText}
              </Text>
              <Text font={TEXT_FONT} fontSize={0.18} color={textColor} anchorX="center" anchorY="top" position={[0, -0.04, 0]} outlineWidth={0.02} outlineColor={outlineColor}>
                {visitsText}
              </Text>
            </Billboard>
          </group>
        );
      })}
    </group>
  );
};

export default memo(BestMoves);
