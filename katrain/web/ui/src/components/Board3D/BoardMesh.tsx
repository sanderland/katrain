import { useMemo, useEffect, useRef, memo, Suspense, lazy } from 'react';
import * as THREE from 'three';
import {
  getBoardDimensions,
  getStarPoints,
  getColumnLabel,
  getRowLabel,
  BOARD_SURFACE_Y,
  SURFACE_EPSILON,
} from './constants';

// Lazy-load coordinate labels so troika-three-text (used by drei <Text>) is only
// fetched when coordinates are actually displayed.  This prevents troika's Web Worker
// from firing CDN requests in headless/offline recording environments.
const CoordinateLabels = lazy(() => import('./CoordinateLabels'));

interface BoardMeshProps {
  boardSize: number;
  showCoordinates: boolean;
}

/** Procedural wood-grain canvas texture. Ported from go-board-3d.html. */
function createWoodTexture(
  width: number, height: number,
  baseColor: string, grainColor: [number, number, number], grainCount: number,
): THREE.CanvasTexture {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext('2d')!;

  ctx.fillStyle = baseColor;
  ctx.fillRect(0, 0, width, height);

  for (let i = 0; i < 12; i++) {
    const y = Math.random() * height;
    const bandH = 20 + Math.random() * 60;
    const grad = ctx.createLinearGradient(0, y, 0, y + bandH);
    grad.addColorStop(0, 'rgba(180, 140, 70, 0)');
    grad.addColorStop(0.5, `rgba(180, 140, 70, ${0.05 + Math.random() * 0.08})`);
    grad.addColorStop(1, 'rgba(180, 140, 70, 0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, y, width, bandH);
  }

  for (let i = 0; i < grainCount; i++) {
    const y = Math.random() * height;
    const alpha = 0.04 + Math.random() * 0.1;
    ctx.strokeStyle = `rgba(${grainColor[0]}, ${grainColor[1]}, ${grainColor[2]}, ${alpha})`;
    ctx.lineWidth = 0.5 + Math.random() * 2.5;
    ctx.beginPath();
    ctx.moveTo(0, y);
    const freq = 0.01 + Math.random() * 0.03;
    const amp = 3 + Math.random() * 12;
    for (let x = 0; x < width; x += 8) {
      ctx.lineTo(x, y + Math.sin(x * freq) * amp + Math.sin(x * 0.005) * 6 + (Math.random() - 0.5) * 2);
    }
    ctx.stroke();
  }

  for (let i = 0; i < grainCount / 3; i++) {
    const y = Math.random() * height;
    ctx.strokeStyle = `rgba(100, 60, 20, ${0.03 + Math.random() * 0.05})`;
    ctx.lineWidth = 2 + Math.random() * 4;
    ctx.beginPath();
    ctx.moveTo(0, y);
    for (let x = 0; x < width; x += 15) {
      ctx.lineTo(x, y + Math.sin(x * 0.015) * 10 + (Math.random() - 0.5) * 3);
    }
    ctx.stroke();
  }

  const imgData = ctx.getImageData(0, 0, width, height);
  const pixels = imgData.data;
  const noiseCount = width * height * 0.3;
  for (let i = 0; i < noiseCount; i++) {
    const idx = Math.floor(Math.random() * width * height) * 4;
    const noise = (Math.random() - 0.5) * 18;
    pixels[idx] = Math.max(0, Math.min(255, pixels[idx] + noise));
    pixels[idx + 1] = Math.max(0, Math.min(255, pixels[idx + 1] + noise));
    pixels[idx + 2] = Math.max(0, Math.min(255, pixels[idx + 2] + noise * 0.5));
  }
  ctx.putImageData(imgData, 0, 0);

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

const BoardMesh = ({ boardSize, showCoordinates }: BoardMeshProps) => {
  const dims = useMemo(() => getBoardDimensions(boardSize), [boardSize]);
  const starPoints = useMemo(() => getStarPoints(boardSize), [boardSize]);
  const halfExtent = dims.boardExtent / 2;

  // Textures with cleanup
  const texturesRef = useRef<THREE.CanvasTexture[]>([]);
  const materialsRef = useRef<THREE.Material[]>([]);

  const { materials } = useMemo(() => {
    const topTex = createWoodTexture(1024, 1024, '#DBA85A', [120, 75, 30], 150);
    const sideTex = createWoodTexture(1024, 256, '#C89848', [110, 70, 28], 120);

    const topMat = new THREE.MeshStandardMaterial({
      map: topTex, roughness: 0.4, metalness: 0.02, color: 0xdba85a,
    });
    const sideMat = new THREE.MeshStandardMaterial({
      map: sideTex, roughness: 0.5, metalness: 0.03, color: 0xc89848,
    });
    const bottomMat = new THREE.MeshStandardMaterial({
      color: 0xb08040, roughness: 0.7, metalness: 0.02,
    });

    texturesRef.current = [topTex, sideTex];
    materialsRef.current = [topMat, sideMat, bottomMat];

    // BoxGeometry face order: +x, -x, +y, -y, +z, -z
    return { materials: [sideMat, sideMat, topMat, bottomMat, sideMat, sideMat] };
  }, [boardSize]);

  // Cleanup on boardSize change and unmount (dispose is a side effect → useEffect, not useMemo)
  useEffect(() => {
    return () => {
      texturesRef.current.forEach(t => t.dispose());
      materialsRef.current.forEach(m => m.dispose());
    };
  }, [boardSize]);

  // Grid lines as a single LineSegments geometry (1 draw call instead of 38)
  const gridGeometry = useMemo(() => {
    const lineY = BOARD_SURFACE_Y + SURFACE_EPSILON;
    const vertices: number[] = [];

    for (let i = 0; i < boardSize; i++) {
      const pos = -halfExtent + i * dims.gridSpacing;
      // Vertical line (pair of endpoints)
      vertices.push(pos, lineY, -halfExtent, pos, lineY, halfExtent);
      // Horizontal line
      vertices.push(-halfExtent, lineY, pos, halfExtent, lineY, pos);
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
    return geom;
  }, [boardSize, dims, halfExtent]);

  useEffect(() => {
    return () => { gridGeometry.dispose(); };
  }, [gridGeometry]);

  // Coordinate label data
  const coordLabels = useMemo(() => {
    if (!showCoordinates) return [];
    const labelOffset = 0.4; // Center of board padding zone (BOARD_PADDING/2)
    const labelY = BOARD_SURFACE_Y + SURFACE_EPSILON;
    const labels: { text: string; position: [number, number, number] }[] = [];

    for (let i = 0; i < boardSize; i++) {
      const xPos = -halfExtent + i * dims.gridSpacing;
      const zPos = halfExtent - i * dims.gridSpacing; // Inverted Z to match gridToWorld convention

      // Column labels (A-T) along near and far edges
      labels.push({ text: getColumnLabel(i), position: [xPos, labelY, halfExtent + labelOffset] });
      labels.push({ text: getColumnLabel(i), position: [xPos, labelY, -halfExtent - labelOffset] });
      // Row labels (1-19) along left and right edges — Z inverted so "1" is near camera
      labels.push({ text: getRowLabel(i), position: [-halfExtent - labelOffset, labelY, zPos] });
      labels.push({ text: getRowLabel(i), position: [halfExtent + labelOffset, labelY, zPos] });
    }
    return labels;
  }, [boardSize, dims, halfExtent, showCoordinates]);

  return (
    <group>
      {/* Board slab */}
      <mesh
        position={[0, dims.boardHeight / 2, 0]}
        material={materials}
        castShadow
        receiveShadow
      >
        <boxGeometry args={[dims.boardWidth, dims.boardHeight, dims.boardWidth]} />
      </mesh>

      {/* Grid lines — single LineSegments for efficiency (1 draw call) */}
      <lineSegments geometry={gridGeometry}>
        <lineBasicMaterial color="black" transparent opacity={0.7} />
      </lineSegments>

      {/* Star points */}
      {starPoints.map(([col, row], i) => {
        const x = -halfExtent + col * dims.gridSpacing;
        const z = -halfExtent + row * dims.gridSpacing;
        return (
          <mesh key={`star-${i}`} position={[x, BOARD_SURFACE_Y + SURFACE_EPSILON, z]} rotation={[-Math.PI / 2, 0, 0]}>
            <circleGeometry args={[0.08, 16]} />
            <meshBasicMaterial color="black" opacity={0.85} transparent />
          </mesh>
        );
      })}

      {/* Coordinate labels — lazy-loaded to avoid troika CDN dependency in headless mode */}
      {showCoordinates && (
        <Suspense fallback={null}>
          <CoordinateLabels labels={coordLabels} />
        </Suspense>
      )}
    </group>
  );
};

export default memo(BoardMesh);
