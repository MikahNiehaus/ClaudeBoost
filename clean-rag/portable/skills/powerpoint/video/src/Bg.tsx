import React from "react";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";
import { C, W, H } from "./theme";

const rnd = (n: number) => {
  const x = Math.sin(n * 127.1 + 311.7) * 43758.5453;
  return x - Math.floor(x);
};
const DOTS = Array.from({ length: 46 }, (_, i) => ({
  x: rnd(i) * W, y: rnd(i + 90) * H, r: 2 + rnd(i + 5) * 5,
  sp: 0.15 + rnd(i + 17) * 0.5, ph: rnd(i + 33) * 6.28, c: i % 3,
}));

export const Bg: React.FC = () => {
  const f = useCurrentFrame();
  const a = interpolate(f % 900, [0, 450, 900], [0, 40, 0]);
  const cols = [C.violet, C.cyan, C.pink];
  return (
    <AbsoluteFill style={{ background: `linear-gradient(${135 + a}deg, ${C.bg1}, ${C.bg2} 60%, #2a1450)` }}>
      <div style={{ position: "absolute", left: -200 + Math.sin(f / 150) * 120, top: -250, width: 900, height: 900,
        borderRadius: "50%", background: `radial-gradient(${C.violet}33, transparent 65%)` }} />
      <div style={{ position: "absolute", right: -250 + Math.cos(f / 190) * 140, bottom: -300, width: 1000, height: 1000,
        borderRadius: "50%", background: `radial-gradient(${C.cyan}22, transparent 65%)` }} />
      <svg width={W} height={H} style={{ position: "absolute", inset: 0 }}>
        {DOTS.map((d, i) => (
          <circle key={i} cx={d.x + Math.sin(f * 0.01 * d.sp + d.ph) * 40}
            cy={(d.y - f * d.sp * 0.6 + H * 4) % H} r={d.r} fill={cols[d.c]} opacity={0.22} />
        ))}
      </svg>
    </AbsoluteFill>
  );
};
