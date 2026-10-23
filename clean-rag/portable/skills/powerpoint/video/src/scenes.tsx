import React from "react";
import { useCurrentFrame, spring, interpolate, useVideoConfig } from "remotion";
import { C, ACCENTS, FONT, W } from "./theme";
import { Scene } from "./types";
import { DEMOS, Badge } from "./demos";

// cueF[i] = frame (relative to scene start) at which item i appears
type P = { s: Scene; cueF: number[]; dur: number };

const useIn = (at: number, damping = 16) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: f - at, fps, config: { damping, stiffness: 110, mass: 0.7 } });
};

const Heading: React.FC<{ text?: string }> = ({ text }) => {
  const p = useIn(0);
  if (!text) return null;
  return (
    <div style={{ position: "absolute", top: 70, left: 120, right: 120, fontSize: 64, fontWeight: 700, color: C.text,
      fontFamily: FONT, opacity: p, transform: `translateY(${(1 - p) * -30}px)`, letterSpacing: -1 }}>
      {text}
      <div style={{ height: 6, width: 160 * p, background: C.violet, borderRadius: 3, marginTop: 14 }} />
    </div>
  );
};

const Area: React.FC<{ children: React.ReactNode; top?: number }> = ({ children, top = 200 }) => (
  <div style={{ position: "absolute", top, left: 120, right: 120, bottom: 300, fontFamily: FONT, color: C.text }}>{children}</div>
);

const Fade: React.FC<{ dur: number; children: React.ReactNode }> = ({ dur, children }) => {
  const f = useCurrentFrame();
  const o = interpolate(f, [0, 10, Math.max(11, dur - 10), Math.max(12, dur)], [0, 1, 1, 0], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  const y = interpolate(f, [0, 12], [24, 0], { extrapolateRight: "clamp" });
  return <div style={{ position: "absolute", inset: 0, opacity: o, transform: `translateY(${y}px)` }}>{children}</div>;
};

const Title: React.FC<P> = ({ s }) => {
  const p = useIn(2, 18);
  const q = useIn(14, 18);
  return (
    <div style={{ position: "absolute", inset: 0, display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", paddingBottom: 200, fontFamily: FONT, color: C.text, textAlign: "center" }}>
      <div style={{ fontSize: 110, fontWeight: 800, letterSpacing: -3, maxWidth: 1500, lineHeight: 1.05,
        opacity: p, transform: `scale(${0.9 + p * 0.1})`, background: `linear-gradient(90deg, ${C.violet}, ${C.cyan})`,
        WebkitBackgroundClip: "text", color: "transparent" }}>{s.title}</div>
      {s.subtitle && <div style={{ fontSize: 44, color: C.dim, marginTop: 30, opacity: q, maxWidth: 1400 }}>{s.subtitle}</div>}
    </div>
  );
};

const Bullet: React.FC<{ t: string; at: number; i: number }> = ({ t, at, i }) => {
  const p = useIn(at);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 28, opacity: p, transform: `translateX(${(1 - p) * -60}px)` }}>
      <div style={{ width: 22, height: 22, borderRadius: 11, flexShrink: 0, background: ACCENTS[i % 5], boxShadow: `0 0 24px ${ACCENTS[i % 5]}` }} />
      <div style={{ fontSize: 54, fontWeight: 600, lineHeight: 1.15 }}>{t}</div>
    </div>
  );
};
const Bullets: React.FC<P> = ({ s, cueF }) => (
  <Area>
    <div style={{ display: "flex", flexDirection: "column", gap: 34, justifyContent: "center", height: "100%" }}>
      {(s.items as string[]).map((t, i) => <Bullet key={i} t={t} at={cueF[i]} i={i} />)}
    </div>
  </Area>
);

const FlowNode: React.FC<{ t: string; i: number; at: number; nextAt: number | null; bw: number; gap: number }> = ({ t, i, at, nextAt, bw, gap }) => {
  const f = useCurrentFrame();
  const p = useIn(at);
  const next = useIn(nextAt === null ? 99999 : nextAt - 6);
  const len = (gap - 14) * next;
  return (
    <>
      <div style={{ width: bw, minHeight: 190, padding: 22, borderRadius: 26, background: C.panel, boxSizing: "border-box",
        border: `3px solid ${ACCENTS[i % 5]}`, display: "flex", alignItems: "center", justifyContent: "center",
        textAlign: "center", fontSize: 40, fontWeight: 600, opacity: p, transform: `scale(${0.7 + p * 0.3})`,
        boxShadow: `0 0 ${30 * p}px ${ACCENTS[i % 5]}55` }}>{t}</div>
      {nextAt !== null && (
        <svg width={gap + 10} height={40} style={{ margin: "0 -5px", opacity: next, flexShrink: 0 }}>
          <line x1={0} y1={20} x2={len} y2={20} stroke={C.violet} strokeWidth={6} strokeLinecap="round"
            strokeDasharray="14 10" strokeDashoffset={-f * 1.2} />
          <polygon points={`${len},8 ${len + 22},20 ${len},32`} fill={C.violet} />
        </svg>
      )}
    </>
  );
};
const Flow: React.FC<P> = ({ s, cueF }) => {
  const nodes = s.nodes as string[];
  const n = nodes.length;
  const gap = 90;
  const bw = Math.min(380, (W - 240 - gap * (n - 1)) / n);
  const loopP = useIn((cueF[n - 1] ?? 0) + 10);
  return (
    <Area>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", height: "100%", gap }}>
        {nodes.map((t, i) => (
          <FlowNode key={i} t={t} i={i} at={cueF[i]} nextAt={i < n - 1 ? cueF[i + 1] : null} bw={bw} gap={gap} />
        ))}
      </div>
      {s.loop && (
        <div style={{ position: "absolute", bottom: 10, left: 0, right: 0, textAlign: "center", fontSize: 38, color: C.cyan, opacity: loopP }}>
          {String(s.loop)}
        </div>
      )}
    </Area>
  );
};

const Item: React.FC<{ t: string; at: number }> = ({ t, at }) => {
  const q = useIn(at);
  return <div style={{ fontSize: 40, lineHeight: 1.2, opacity: q, transform: `translateX(${(1 - q) * 30}px)` }}>{"• "}{t}</div>;
};
const Side: React.FC<{ d: any; at: number; color: string; cues: number[]; off: number }> = ({ d, at, color, cues, off }) => {
  const p = useIn(at);
  return (
    <div style={{ flex: 1, padding: 36, borderRadius: 30, background: C.panel, border: `3px solid ${color}`, boxSizing: "border-box",
      opacity: p, transform: `translateY(${(1 - p) * 40}px)`, display: "flex", flexDirection: "column", gap: 22 }}>
      <div style={{ fontSize: 56, fontWeight: 800, color }}>{d.title}</div>
      {(d.items as string[]).map((t, i) => <Item key={i} t={t} at={cues[off + i] ?? at + 10 + i * 8} />)}
    </div>
  );
};
const Compare: React.FC<P> = ({ s, cueF }) => {
  const nl = (s.left.items as string[]).length;
  return (
    <Area>
      <div style={{ display: "flex", gap: 50, height: "100%", alignItems: "stretch" }}>
        <Side d={s.left} at={0} color={C.cyan} cues={cueF} off={0} />
        <Side d={s.right} at={Math.max(0, Math.round((cueF[nl] ?? 40) - 12))} color={C.pink} cues={cueF} off={nl} />
      </div>
    </Area>
  );
};

const Stat: React.FC<P> = ({ s }) => {
  const p = useIn(2, 20);
  const n = useIn(30);
  const f = useCurrentFrame();
  const v = String(s.value);
  const m = v.match(/[0-9][0-9,]*\.?[0-9]*/);
  let shown = v;
  if (m) {
    const num = parseFloat(m[0].replace(/,/g, ""));
    const dec = (m[0].split(".")[1] || "").length;
    const cur = num * Math.min(1, f / 40);
    shown = v.replace(m[0], dec ? cur.toFixed(dec) : Math.round(cur).toLocaleString("en-US"));
  }
  return (
    <div style={{ position: "absolute", inset: 0, paddingBottom: 280, display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", fontFamily: FONT, color: C.text, textAlign: "center" }}>
      <div style={{ fontSize: 220, fontWeight: 800, color: C.amber, opacity: p, transform: `scale(${0.8 + 0.2 * p})`,
        textShadow: `0 0 60px ${C.amber}66`, lineHeight: 1 }}>{shown}</div>
      <div style={{ fontSize: 60, fontWeight: 600, marginTop: 24, opacity: p, maxWidth: 1500 }}>{s.label}</div>
      {s.note && <div style={{ fontSize: 38, color: C.dim, marginTop: 24, opacity: n, maxWidth: 1400 }}>{s.note}</div>}
    </div>
  );
};

const Step: React.FC<{ t: string; i: number; at: number }> = ({ t, i, at }) => {
  const p = useIn(at);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 30, opacity: p, transform: `translateX(${(1 - p) * 80}px)` }}>
      <div style={{ width: 84, height: 84, borderRadius: 42, background: ACCENTS[i % 5], color: C.bg1, fontSize: 48, fontWeight: 800,
        display: "flex", alignItems: "center", justifyContent: "center", flexShrink: 0 }}>{i + 1}</div>
      <div style={{ fontSize: 50, fontWeight: 600, lineHeight: 1.15 }}>{t}</div>
    </div>
  );
};
const Steps: React.FC<P> = ({ s, cueF }) => (
  <Area>
    <div style={{ display: "flex", flexDirection: "column", gap: 26, justifyContent: "center", height: "100%" }}>
      {(s.items as string[]).map((t, i) => <Step key={i} t={t} i={i} at={cueF[i]} />)}
    </div>
  </Area>
);

const Term: React.FC<P> = ({ s }) => {
  const p = useIn(2);
  const q = useIn(20);
  return (
    <div style={{ position: "absolute", inset: 0, boxSizing: "border-box", display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", fontFamily: FONT, color: C.text, textAlign: "center", padding: "0 200px 260px" }}>
      <div style={{ fontSize: 120, fontWeight: 800, color: C.cyan, opacity: p, transform: `scale(${0.85 + 0.15 * p})`, lineHeight: 1.05 }}>{s.term}</div>
      <div style={{ height: 6, width: 300 * p, background: C.violet, margin: "30px 0", borderRadius: 3 }} />
      <div style={{ fontSize: 56, lineHeight: 1.25, opacity: q, transform: `translateY(${(1 - q) * 20}px)`, maxWidth: 1400 }}>{s.definition}</div>
    </div>
  );
};

const GNode: React.FC<{ t: string; i: number; at: number; x: number; y: number }> = ({ t, i, at, x, y }) => {
  const p = useIn(at);
  return (
    <g transform={`translate(${x},${y}) scale(${p})`} opacity={p}>
      <circle r={66} fill={C.bg2} stroke={ACCENTS[i % 5]} strokeWidth={5} />
      <text textAnchor="middle" y={11} fontSize={t.length > 9 ? 24 : 32} fontWeight={700} fill={C.text} fontFamily={FONT}>{t}</text>
    </g>
  );
};
const GEdge: React.FC<{ at: number; a: number[]; b: number[] }> = ({ at, a, b }) => {
  const p = useIn(at);
  return <line x1={a[0]} y1={a[1]} x2={a[0] + (b[0] - a[0]) * p} y2={a[1] + (b[1] - a[1]) * p} stroke={C.violet} strokeOpacity={0.6} strokeWidth={5} />;
};
const Graph: React.FC<P> = ({ s, cueF }) => {
  const nodes = s.nodes as string[];
  const edges = (s.edges || []) as [number, number][];
  const n = nodes.length;
  const cx = (W - 240) / 2, cy = 260, R = 215;
  const layout = s.layout || "cycle";
  const pos = nodes.map((_, i) => {
    if (layout === "star") {
      if (i === 0) return [cx, cy];
      const a = ((i - 1) / Math.max(1, n - 1)) * Math.PI * 2 - Math.PI / 2;
      return [cx + Math.cos(a) * R * 1.6, cy + Math.sin(a) * R];
    }
    if (layout === "layers") {
      const cols = Math.ceil(Math.sqrt(n));
      return [cx - 450 + (i % cols) * (900 / Math.max(1, cols - 1)), cy - 120 + Math.floor(i / cols) * 200];
    }
    const a = (i / n) * Math.PI * 2 - Math.PI / 2;
    return [cx + Math.cos(a) * R * 1.6, cy + Math.sin(a) * R];
  });
  return (
    <Area>
      <svg width={W - 240} height={560} style={{ position: "absolute", inset: 0 }}>
        {edges.map(([a, b], k) => <GEdge key={k} at={Math.max(cueF[a] ?? 0, cueF[b] ?? 0) + 6} a={pos[a]} b={pos[b]} />)}
        {nodes.map((t, i) => <GNode key={i} t={t} i={i} at={cueF[i]} x={pos[i][0]} y={pos[i][1]} />)}
      </svg>
    </Area>
  );
};

const Quote: React.FC<P> = ({ s }) => {
  const p = useIn(2);
  const q = useIn(20);
  return (
    <div style={{ position: "absolute", inset: 0, boxSizing: "border-box", display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", fontFamily: FONT, color: C.text, textAlign: "center", padding: "0 220px 260px" }}>
      <div style={{ fontSize: 150, color: C.violet, lineHeight: 0.6, opacity: p }}>{"“"}</div>
      <div style={{ fontSize: 66, fontWeight: 600, lineHeight: 1.25, opacity: p, fontStyle: "italic" }}>{s.text}</div>
      {s.by && <div style={{ fontSize: 38, color: C.dim, marginTop: 30, opacity: q }}>{s.by}</div>}
    </div>
  );
};

const MAP: Record<string, React.FC<P>> = {
  ...DEMOS, title: Title, bullets: Bullets, flow: Flow, compare: Compare, stat: Stat, steps: Steps, term: Term, graph: Graph, quote: Quote,
};

export const SceneView: React.FC<P> = (props) => {
  const K = MAP[props.s.kind] || Bullets;
  return (
    <Fade dur={props.dur}>
      {props.s.kind !== "title" && <Heading text={props.s.heading} />}
      {props.s.kind in DEMOS && <Badge />}
      <K {...props} />
    </Fade>
  );
};
