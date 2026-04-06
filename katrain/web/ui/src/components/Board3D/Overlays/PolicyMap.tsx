import { useMemo, memo } from 'react';
import { Billboard, Text } from '@react-three/drei';
import { gridToSurface, EVAL_COLORS, BOARD_SURFACE_Y, STONE_HEIGHT, TEXT_FONT } from '../constants';
import type { GameState } from '../../../api';

interface PolicyMapProps {
  gameState: GameState;
}

const PolicyMap = ({ gameState }: PolicyMapProps) => {
  const boardSize = gameState.board_size[0];
  const policy = gameState.analysis?.policy;

  const cells = useMemo(() => {
    if (!policy) return [];
    const result: { pos: [number, number, number]; color: string; prob: number }[] = [];
    for (let y = 0; y < boardSize; y++) {
      for (let x = 0; x < boardSize; x++) {
        const prob = policy[y][x];
        if (prob > 0.001) {
          const polOrder = Math.max(0, 5 + Math.floor(Math.log10(Math.max(1e-9, prob - 1e-9))));
          result.push({
            pos: gridToSurface(x, y, boardSize),
            color: EVAL_COLORS[Math.min(polOrder, 5)],
            prob,
          });
        }
      }
    }
    return result;
  }, [policy, boardSize]);

  return (
    <group>
      {cells.map((cell, i) => (
        <group key={i}>
          <mesh position={cell.pos} rotation={[-Math.PI / 2, 0, 0]}>
            <circleGeometry args={[0.28, 16]} />
            <meshBasicMaterial color={cell.color} transparent opacity={0.5} depthWrite={false} />
          </mesh>
          {cell.prob > 0.01 && (
            <Billboard position={[cell.pos[0], BOARD_SURFACE_Y + STONE_HEIGHT * 0.5, cell.pos[2]]}>
              <Text
                font={TEXT_FONT}
                fontSize={0.2}
                color="#ffffff"
                anchorX="center"
                anchorY="middle"
                outlineWidth={0.015}
                outlineColor="#000000"
              >
                {`${(cell.prob * 100).toFixed(0)}%`}
              </Text>
            </Billboard>
          )}
        </group>
      ))}
    </group>
  );
};

export default memo(PolicyMap);
