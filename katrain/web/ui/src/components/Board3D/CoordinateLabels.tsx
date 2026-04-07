import { memo } from 'react';
import { Text } from '@react-three/drei';
import { TEXT_FONT } from './constants';

interface CoordinateLabelsProps {
  labels: { text: string; position: [number, number, number] }[];
}

const CoordinateLabels = ({ labels }: CoordinateLabelsProps) => (
  <group>
    {labels.map((label, i) => (
      <Text
        key={`coord-${i}`}
        font={TEXT_FONT}
        position={label.position}
        rotation={[-Math.PI / 2, 0, 0]}
        fontSize={0.38}
        color="#2a1a0a"
        fillOpacity={0.8}
        anchorX="center"
        anchorY="middle"
      >
        {label.text}
      </Text>
    ))}
  </group>
);

export default memo(CoordinateLabels);
