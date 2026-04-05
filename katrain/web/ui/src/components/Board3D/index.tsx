import { useState, useCallback, useRef, useEffect, memo } from 'react';
import { Canvas, useFrame, useThree, type RootState } from '@react-three/fiber';
import * as THREE from 'three';
import { ACESFilmicToneMapping, PCFShadowMap } from 'three';
import Lights from './Lights';
import BoardMesh from './BoardMesh';
import CameraController from './CameraController';
import StoneGroup from './StoneGroup';
import RaycastClick from './RaycastClick';
import GhostStone from './GhostStone';
import Territory from './Overlays/Territory';
import LastMove from './Overlays/LastMove';
import EvalDots from './Overlays/EvalDots';
import BestMoves from './Overlays/BestMoves';
import PolicyMap from './Overlays/PolicyMap';
import MoveNumbers from './Overlays/MoveNumbers';
import type { BoardProps } from '../Board';

/** Static camera for recording mode — sets position + lookAt once, no interaction */
const StaticCamera = ({ position, target }: { position: [number, number, number]; target: [number, number, number] }) => {
  const { camera } = useThree();
  useEffect(() => {
    camera.position.set(...position);
    camera.lookAt(new THREE.Vector3(...target));
    camera.updateProjectionMatrix();
  }, [camera, position, target]);
  return null;
};

/** Syncs OrbitControls polar angle → external state callback each frame */
const PolarSync = ({ orbitRef, onPolarChange }: { orbitRef: React.RefObject<any>; onPolarChange: (angle: number) => void }) => {
  useFrame(() => {
    const controls = orbitRef.current;
    if (controls) {
      onPolarChange(controls.getPolarAngle());
    }
  });
  return null;
};

interface Board3DProps extends BoardProps {
  cameraPosition?: [number, number, number];
  cameraTarget?: [number, number, number];
  disableControls?: boolean;
  /** Lock polar angle for non-interactive mode (fraction of π, e.g., 0.33) */
  fixedPolarAngle?: number;
}

const Board3D = ({ gameState, onMove, onNavigate, analysisToggles, playerColor, cameraPosition, cameraTarget, disableControls, fixedPolarAngle }: Board3DProps) => {
  const boardSize = gameState.board_size[0];
  const orbitRef = useRef<any>(null);
  const [polarAngle, setPolarAngle] = useState(Math.PI * 0.2); // initial approx

  const [hoverPos, setHoverPos] = useState<{ col: number; row: number } | null>(null);
  const handleHover = useCallback((pos: { col: number; row: number } | null) => {
    setHoverPos(pos);
  }, []);

  // Throttle polar angle updates to avoid excessive re-renders
  const lastPolarRef = useRef(polarAngle);
  const handlePolarChange = useCallback((angle: number) => {
    if (Math.abs(angle - lastPolarRef.current) > 0.01) {
      lastPolarRef.current = angle;
      setPolarAngle(angle);
    }
  }, []);

  // Force initial render: R3F Canvas may miss the first frame after dynamic import
  const handleCreated = useCallback((state: RootState) => {
    const { gl, invalidate } = state;
    gl.setSize(gl.domElement.clientWidth, gl.domElement.clientHeight);
    invalidate();
  }, []);

  const handleTiltChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const controls = orbitRef.current;
    if (!controls) return;
    const newAngle = parseFloat(e.target.value);
    controls.minPolarAngle = newAngle;
    controls.maxPolarAngle = newAngle;
    controls.update();
    // Restore limits after forcing the angle
    requestAnimationFrame(() => {
      if (orbitRef.current) {
        orbitRef.current.minPolarAngle = Math.PI * 0.05;
        orbitRef.current.maxPolarAngle = Math.PI * 0.38;
      }
    });
  }, []);

  const handleZoom = useCallback((direction: 'in' | 'out') => {
    const controls = orbitRef.current;
    if (!controls) return;
    const factor = direction === 'in' ? 0.8 : 1.25;
    const camera = controls.object;
    const offset = camera.position.clone().sub(controls.target);
    offset.multiplyScalar(factor);
    camera.position.copy(controls.target).add(offset);
    controls.update();
  }, []);

  const minPolar = Math.PI * 0.05;
  const maxPolar = Math.PI * 0.38;

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
      <Canvas
        shadows={{ type: PCFShadowMap }}
        camera={{ position: cameraPosition || [0, 22, 26], fov: 40, near: 0.1, far: 100 }}
        gl={{ antialias: true, toneMapping: ACESFilmicToneMapping, toneMappingExposure: 1.2 }}
        style={{ borderRadius: '4px', cursor: 'pointer' }}
        onCreated={handleCreated}
      >
        <color attach="background" args={['#0f0f0f']} />
        <fog attach="fog" args={['#0f0f0f', 30, 60]} />
        <Lights />
        {disableControls && cameraPosition && cameraTarget ? (
          <StaticCamera position={cameraPosition} target={cameraTarget} />
        ) : (
          <>
            <CameraController ref={orbitRef} target={cameraTarget} interactive={!disableControls} fixedPolarAngle={fixedPolarAngle} />
            <PolarSync orbitRef={orbitRef} onPolarChange={handlePolarChange} />
          </>
        )}
        <BoardMesh boardSize={boardSize} showCoordinates={!!analysisToggles.coords} />
        <StoneGroup gameState={gameState} enableDropEffect={!!analysisToggles.stoneDropEffect} />
        <RaycastClick
          gameState={gameState}
          onMove={onMove}
          onNavigate={onNavigate}
          playerColor={playerColor}
          onHover={handleHover}
        />
        <GhostStone gameState={gameState} hoverPos={hoverPos} showChildren={!!analysisToggles.children} playerColor={playerColor} />

        {/* Analysis Overlays */}
        <LastMove gameState={gameState} />
        {analysisToggles.numbers && <MoveNumbers gameState={gameState} />}
        {analysisToggles.ownership && gameState.analysis?.ownership && (
          <Territory gameState={gameState} />
        )}
        {analysisToggles.eval && <EvalDots gameState={gameState} />}
        {analysisToggles.hints && <BestMoves gameState={gameState} />}
        {analysisToggles.policy && gameState.analysis?.policy && (
          <PolicyMap gameState={gameState} />
        )}
      </Canvas>

      {/* Tilt & Zoom Controls Overlay */}
      {!disableControls && <div style={{
        position: 'absolute',
        bottom: 16,
        right: 16,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 4,
        background: 'rgba(0,0,0,0.5)',
        borderRadius: 8,
        padding: '8px 6px',
        backdropFilter: 'blur(4px)',
        userSelect: 'none',
      }}>
        <button
          onClick={() => handleZoom('in')}
          style={{
            width: 28, height: 28,
            border: '1px solid rgba(255,255,255,0.2)',
            borderRadius: 4,
            background: 'rgba(255,255,255,0.1)',
            color: '#fff',
            fontSize: 16,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            lineHeight: 1,
          }}
          title="Zoom in"
        >+</button>
        <button
          onClick={() => handleZoom('out')}
          style={{
            width: 28, height: 28,
            border: '1px solid rgba(255,255,255,0.2)',
            borderRadius: 4,
            background: 'rgba(255,255,255,0.1)',
            color: '#fff',
            fontSize: 16,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            lineHeight: 1,
          }}
          title="Zoom out"
        >&minus;</button>
        <input
          type="range"
          min={minPolar}
          max={maxPolar}
          step={0.01}
          value={polarAngle}
          onChange={handleTiltChange}
          title="Tilt angle"
          style={{
            writingMode: 'vertical-lr',
            direction: 'rtl',
            width: 28,
            height: 80,
            accentColor: '#90caf9',
            cursor: 'pointer',
            margin: '2px 0',
          }}
        />
      </div>}

      {/* End-game result overlay (HTML layer on top of Canvas) */}
      {gameState.end_result && (
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'rgba(0, 0, 0, 0.6)',
          borderRadius: '4px', pointerEvents: 'none',
        }}>
          <span style={{ color: '#fff', fontSize: '2rem', fontWeight: 'bold', textAlign: 'center' }}>
            {gameState.end_result}
          </span>
        </div>
      )}
    </div>
  );
};

export default memo(Board3D);
