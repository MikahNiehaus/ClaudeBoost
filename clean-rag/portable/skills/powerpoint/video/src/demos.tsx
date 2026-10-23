import React from "react";
import { useCurrentFrame, spring, interpolate, useVideoConfig } from "remotion";
import { C, ACCENTS, FONT, W } from "./theme";
import { Scene } from "./types";

type P = { s: Scene; cueF: number[]; dur: number };
const MONO = "Consolas, 'Courier New', monospace";

const useIn = (at: number, damping = 16) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  return spring({ frame: f - at, fps, config: { damping, stiffness: 110, mass: 0.7 } });
};
const Area: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ position: "absolute", top: 200, left: 120, right: 120, bottom: 300, fontFamily: FONT, color: C.text }}>{children}</div>
);
export const Badge: React.FC = () => (
  <div style={{ position: "absolute", top: 86, right: 120, fontSize: 28, fontWeight: 700, color: C.bg1, background: C.amber,
    padding: "6px 18px", borderRadius: 20, fontFamily: FONT, letterSpacing: 2 }}>EXAMPLE</div>
);
const typed = (text: string, at: number, f: number, cps = 38) =>
  text.slice(0, Math.max(0, Math.min(text.length, Math.floor(((f - at) / 30) * cps))));

const DocRow: React.FC<{ d: any; at: number; pick: boolean }> = ({ d, at, pick }) => {
  const p = useIn(at);
  const bar = useIn(at + 6, 20);
  const col = pick ? C.green : C.violet;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 24, opacity: p, transform: `translateX(${(1 - p) * -50}px)`,
      padding: "14px 26px", borderRadius: 20, background: C.panel, border: `3px solid ${pick ? C.green : "transparent"}`,
      boxShadow: pick ? `0 0 ${30 * bar}px ${C.green}66` : "none" }}>
      <div style={{ flex: 1, fontSize: 36, fontWeight: 600, minWidth: 0 }}>{d.text}</div>
      <div style={{ width: 300, height: 26, borderRadius: 13, background: "#ffffff14", flexShrink: 0 }}>
        <div style={{ width: `${Math.round(d.score * 100 * bar)}%`, height: "100%", borderRadius: 13, background: col }} />
      </div>
      <div style={{ width: 90, fontSize: 36, fontWeight: 800, color: col, textAlign: "right" }}>{(d.score * bar).toFixed(2)}</div>
    </div>
  );
};
export const Search: React.FC<P> = ({ s, cueF }) => {
  const f = useCurrentFrame();
  const docs = s.docs as any[];
  const pick = (s.pick || []) as number[];
  const qa = useIn(0);
  return (
    <Area>
      <div style={{ opacity: qa, fontSize: 44, fontWeight: 700, color: C.cyan, marginBottom: 26 }}>
        {"Query  "}<span style={{ color: C.text }}>{typed(String(s.query), 4, f)}</span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        {docs.map((d, i) => <DocRow key={i} d={d} at={cueF[i] ?? 30 + i * 12} pick={pick.includes(i)} />)}
      </div>
    </Area>
  );
};

export const Walk: React.FC<P> = ({ s, cueF }) => {
  const f = useCurrentFrame();
  const nodes = s.nodes as string[];
  const edges = (s.edges || []) as [number, number][];
  const path = (s.path || []) as number[];
  const n = nodes.length;
  const cx = (W - 240) / 2, cy = 280, R = 185;
  const lay = s.layout || "cycle";
  const pos = nodes.map((_, i) => {
    if (lay === "star") {
      if (i === 0) return [cx, cy];
      const a = ((i - 1) / Math.max(1, n - 1)) * Math.PI * 2 - Math.PI / 2;
      return [cx + Math.cos(a) * R * 1.6, cy + Math.sin(a) * R];
    }
    const a = (i / n) * Math.PI * 2 - Math.PI / 2;
    return [cx + Math.cos(a) * R * 1.6, cy + Math.sin(a) * R];
  });
  const reach = path.map((_, k) => cueF[k] ?? 20 + k * 25);
  return (
    <Area>
      <svg width={W - 240} height={560} style={{ position: "absolute", inset: 0 }}>
        {edges.map(([a, b], k) => (
          <line key={k} x1={pos[a][0]} y1={pos[a][1]} x2={pos[b][0]} y2={pos[b][1]} stroke={C.violet} strokeOpacity={0.35} strokeWidth={5} />
        ))}
        {path.slice(1).map((to, k) => {
          const a = pos[path[k]], b = pos[to];
          const p = interpolate(f, [reach[k], reach[k + 1]], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const x = a[0] + (b[0] - a[0]) * p, y = a[1] + (b[1] - a[1]) * p;
          return (
            <g key={k}>
              <line x1={a[0]} y1={a[1]} x2={x} y2={y} stroke={C.amber} strokeWidth={9} strokeLinecap="round" />
              {p > 0 && p < 1 && <circle cx={x} cy={y} r={16} fill={C.amber} />}
            </g>
          );
        })}
        {nodes.map((t, i) => {
          const k = path.indexOf(i);
          const on = k >= 0 && f >= reach[k];
          const sc = on ? 1 + 0.12 * Math.max(0, 1 - (f - reach[k]) / 12) : 1;
          return (
            <g key={i} transform={`translate(${pos[i][0]},${pos[i][1]}) scale(${sc})`}>
              <circle r={66} fill={on ? C.amber : C.bg2} stroke={on ? C.amber : ACCENTS[i % 5]} strokeWidth={5} />
              <text textAnchor="middle" y={11} fontSize={t.length > 9 ? 24 : 32} fontWeight={700} fill={on ? C.bg1 : C.text} fontFamily={FONT}>{t}</text>
            </g>
          );
        })}
      </svg>
    </Area>
  );
};

export const Trace: React.FC<P> = ({ s, cueF }) => {
  const f = useCurrentFrame();
  const nodes = s.nodes as string[];
  const data = (s.data || []) as string[];
  const n = nodes.length;
  const gap = 70;
  const bw = Math.min(360, (W - 240 - gap * (n - 1)) / n);
  const x = (i: number) => i * (bw + gap) + bw / 2;
  const reach = nodes.map((_, i) => cueF[i] ?? 20 + i * 30);
  const total = n * (bw + gap) - gap;
  let px = x(0);
  for (let i = 0; i < n - 1; i++) {
    if (f >= reach[i]) px = interpolate(f, [reach[i], reach[i + 1]], [x(i), x(i + 1)], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  }
  return (
    <Area>
      <div style={{ position: "absolute", left: (W - 240 - total) / 2, top: 20, width: total }}>
        <div style={{ position: "relative", height: 170 }}>
          {nodes.map((t, i) => {
            const on = f >= reach[i];
            return (
              <div key={i} style={{ position: "absolute", left: x(i) - bw / 2, width: bw, height: 170, boxSizing: "border-box", borderRadius: 26,
                background: on ? C.panel : "#ffffff08", border: `3px solid ${on ? ACCENTS[i % 5] : "#ffffff22"}`, display: "flex",
                alignItems: "center", justifyContent: "center", textAlign: "center", fontSize: 36, fontWeight: 700, padding: 14,
                boxShadow: on ? `0 0 28px ${ACCENTS[i % 5]}55` : "none" }}>{t}</div>
            );
          })}
        </div>
        <svg width={total} height={60} style={{ display: "block", marginTop: 6 }}>
          <line x1={x(0)} y1={30} x2={x(n - 1)} y2={30} stroke="#ffffff22" strokeWidth={6} strokeLinecap="round" />
          <circle cx={px} cy={30} r={20} fill={C.amber} />
        </svg>
        <div style={{ position: "relative", height: 260 }}>
          {data.map((d, i) => (
            <div key={i} style={{ position: "absolute", left: x(i) - bw / 2, width: bw, boxSizing: "border-box", opacity: f >= reach[i] ? 1 : 0,
              fontFamily: MONO, fontSize: 28, lineHeight: 1.3, color: C.amber, background: "#00000055",
              borderRadius: 16, padding: 16, minHeight: 100, wordBreak: "break-word" }}>{typed(d, reach[i] + 4, f, 45)}</div>
          ))}
        </div>
      </div>
    </Area>
  );
};

export const Code: React.FC<P> = ({ s, cueF }) => {
  const f = useCurrentFrame();
  const lines = s.lines as string[];
  const reach = lines.map((_, i) => cueF[i] ?? 10 + i * 20);
  let cur = -1;
  reach.forEach((r, i) => { if (f >= r) cur = i; });
  return (
    <Area>
      <div style={{ background: "#07040f", border: `2px solid ${C.line}`, borderRadius: 24, padding: "30px 40px", height: "100%",
        boxSizing: "border-box", fontFamily: MONO, fontSize: 38, lineHeight: 1.5, overflow: "hidden" }}>
        {lines.map((l, i) => {
          if (f < reach[i]) return <div key={i} style={{ height: 57 }} />;
          const on = i === cur;
          return (
            <div key={i} style={{ whiteSpace: "pre", color: on ? C.text : C.dim, background: on ? "#a78bfa22" : "transparent",
              borderLeft: `6px solid ${on ? C.amber : "transparent"}`, paddingLeft: 18, marginLeft: -24, height: 57 }}>
              {typed(l, reach[i], f, 60)}{on && Math.floor(f / 8) % 2 === 0 ? "|" : ""}
            </div>
          );
        })}
      </div>
    </Area>
  );
};

export const Chat: React.FC<P> = ({ s, cueF }) => {
  const f = useCurrentFrame();
  const msgs = s.messages as { who: string; text: string }[];
  return (
    <Area>
      <div style={{ display: "flex", flexDirection: "column", gap: 22, justifyContent: "center", height: "100%" }}>
        {msgs.map((m, i) => {
          const at = cueF[i] ?? 10 + i * 40;
          if (f < at) return null;
          const right = m.who !== "user" && m.who !== "attacker" && m.who !== "client";
          const col = m.who === "attacker" ? C.pink : right ? C.cyan : C.violet;
          const p = Math.min(1, (f - at) / 8);
          return (
            <div key={i} style={{ alignSelf: right ? "flex-end" : "flex-start", maxWidth: 1250, opacity: p, transform: `translateY(${(1 - p) * 20}px)` }}>
              <div style={{ fontSize: 26, fontWeight: 700, color: col, marginBottom: 6, textAlign: right ? "right" : "left", letterSpacing: 2 }}>
                {m.who.toUpperCase()}
              </div>
              <div style={{ fontSize: 38, lineHeight: 1.3, padding: "20px 30px", borderRadius: 26, background: C.panel, border: `3px solid ${col}` }}>
                {typed(m.text, at, f, 55)}
              </div>
            </div>
          );
        })}
      </div>
    </Area>
  );
};

const BarRow: React.FC<{ b: any; i: number; at: number; max: number; unit: string }> = ({ b, i, at, max, unit }) => {
  const p = useIn(at, 24);
  const q = Math.min(1, p);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 28, opacity: Math.min(1, p * 2) }}>
      <div style={{ width: 380, fontSize: 40, fontWeight: 600, textAlign: "right" }}>{b.label}</div>
      <div style={{ flex: 1, height: 56, borderRadius: 28, background: "#ffffff12" }}>
        <div style={{ width: `${(b.value / max) * 100 * q}%`, height: "100%", borderRadius: 28, background: ACCENTS[i % 5],
          boxShadow: `0 0 24px ${ACCENTS[i % 5]}77` }} />
      </div>
      <div style={{ width: 170, fontSize: 44, fontWeight: 800, color: ACCENTS[i % 5] }}>
        {(b.value * q).toLocaleString("en-US", { maximumFractionDigits: 2 })}{unit}
      </div>
    </div>
  );
};
export const Bars: React.FC<P> = ({ s, cueF }) => {
  const bars = s.bars as { label: string; value: number }[];
  const max = Number(s.max) || Math.max(...bars.map((b) => b.value));
  return (
    <Area>
      <div style={{ display: "flex", flexDirection: "column", gap: 26, justifyContent: "center", height: "100%" }}>
        {bars.map((b, i) => <BarRow key={i} b={b} i={i} at={cueF[i] ?? 10 + i * 20} max={max} unit={String(s.unit || "")} />)}
      </div>
    </Area>
  );
};

export const DEMOS: Record<string, React.FC<P>> = { search: Search, walk: Walk, trace: Trace, code: Code, chat: Chat, bars: Bars };
