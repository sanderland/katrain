import { memo } from 'react';
import { Billboard, Text } from '@react-three/drei';
import { gridToWorld, STONE_HEIGHT, TEXT_FONT } from '../constants';
import type { GameState } from '../../../api';

interface MoveNumbersProps {
  gameState: GameState;
}

const MoveNumbers = ({ gameState }: MoveNumbersProps) => {
  const boardSize = gameState.board_size[0];

  return (
    <group>
      {gameState.stones.map(([player, coords, , moveNumber]) => {
        if (!coords || moveNumber == null) return null;
        const [x, y] = coords;
        const pos = gridToWorld(x, y, boardSize);
        const textColor = player === 'B' ? '#ffffff' : '#000000';
        const outlineColor = player === 'B' ? '#000000' : '#ffffff';

        return (
          <Billboard key={`mn-${x}-${y}`} position={[pos[0], pos[1] + STONE_HEIGHT + 0.20, pos[2]]}>
            <Text
              font={TEXT_FONT}
              fontSize={0.28}
              color={textColor}
              anchorX="center"
              anchorY="middle"
              outlineWidth={0.015}
              outlineColor={outlineColor}
            >
              {moveNumber}
            </Text>
          </Billboard>
        );
      })}
    </group>
  );
};

export default memo(MoveNumbers);
