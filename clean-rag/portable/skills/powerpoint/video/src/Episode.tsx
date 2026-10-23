import React, { useMemo } from "react";
import { AbsoluteFill, Sequence, useCurrentFrame } from "remotion";
import { Bg } from "./Bg";
import { SceneView } from "./scenes";
import { C, FONT, FPS } from "./theme";
import { Props, Scene, Word } from "./types";

const itemCount = (s: Scene): number => {
  if (s.kind === "compare") return (s.left?.items?.length ?? 0) + (s.right?.items?.length ?? 0);
  if (s.kind === "flow" || s.kind === "graph") return s.nodes?.length ?? 0;
  if (s.kind === "trace") return s.nodes?.length ?? 0;
  if (s.kind === "walk") return s.path?.length ?? 0;
  if (s.kind === "search") return s.docs?.length ?? 0;
  if (s.kind === "code") return s.lines?.length ?? 0;
  if (s.kind === "chat") return s.messages?.length ?? 0;
  if (s.kind === "bars") return s.bars?.length ?? 0;
  return s.items?.length ?? 1;
};

type Timed = { s: Scene; from: number; to: number; cueF: number[] };

const plan = (p: Props): Timed[] => {
  const paras = p.map.paragraphs;
  const starts = p.storyboard.scenes.map((s) => {
    const para = paras[s.para];
    const words = para?.words ?? [];
    if (s.w !== undefined && words[s.w]) return words[s.w].s;
    return s.para === 0 ? 0 : para?.start ?? 0;
  });
  return p.storyboard.scenes.map((s, i) => {
    const from = i === 0 ? 0 : starts[i];
    const to = i + 1 < starts.length ? starts[i + 1] : p.map.duration;
    const words = paras[s.para]?.words ?? [];
    const n = itemCount(s);
    const dur = Math.max(0.5, to - from);
    const cueF = Array.from({ length: n }, (_, k) => {
      const c = s.cues?.[k];
      if (c !== undefined && words[c]) return Math.max(0, Math.round((words[c].s - from) * FPS));
      return Math.round((0.4 + (k / Math.max(1, n)) * dur * 0.75) * FPS);
    });
    for (let k = 1; k < cueF.length; k++) cueF[k] = Math.max(cueF[k], cueF[k - 1] + 1);
    return { s, from: Math.round(from * FPS), to: Math.round(to * FPS), cueF };
  });
};

type Chunk = { words: Word[]; start: number; end: number };
const chunks = (p: Props): Chunk[] => {
  const out: Chunk[] = [];
  for (const para of p.map.paragraphs) {
    let cur: Word[] = [];
    const flush = () => {
      if (cur.length) out.push({ words: cur, start: cur[0].s, end: cur[cur.length - 1].e });
      cur = [];
    };
    for (const w of para.words) {
      cur.push(w);
      const endSent = /[.?!]["')]*$/.test(w.w);
      const soft = cur.length >= 12 && /[,;]$/.test(w.w);
      if (endSent || soft || cur.length >= 20) flush();
    }
    flush();
  }
  return out;
};

const Captions: React.FC<{ ch: Chunk[] }> = ({ ch }) => {
  const t = useCurrentFrame() / FPS;
  let idx = ch.findIndex((c) => t >= c.start && t < c.end + 0.25);
  if (idx < 0) idx = Math.max(0, ch.findIndex((c) => c.start > t) - 1);
  const c = ch[idx];
  if (!c) return null;
  return (
    <div style={{ position: "absolute", left: 160, right: 160, bottom: 70, height: 200, display: "flex", alignItems: "center",
      justifyContent: "center", textAlign: "center", fontFamily: FONT, fontSize: 48, fontWeight: 600, lineHeight: 1.3,
      background: "rgba(10,6,22,0.62)", borderRadius: 28, padding: "10px 40px", border: `2px solid ${C.line}` }}>
      <div>
        {c.words.map((w, i) => {
          const on = t >= w.s && t < w.e + 0.02;
          const past = t >= w.e;
          return (
            <span key={i} style={{ color: on ? C.amber : past ? C.text : C.dim, transition: "none" }}>{w.w}{" "}</span>
          );
        })}
      </div>
    </div>
  );
};

export const Episode: React.FC<Props> = (props) => {
  const timed = useMemo(() => plan(props), [props]);
  const ch = useMemo(() => chunks(props), [props]);
  return (
    <AbsoluteFill>
      <Bg />
      {timed.map((t, i) => (
        <Sequence key={i} from={t.from} durationInFrames={Math.max(1, t.to - t.from)} layout="none">
          <SceneView s={t.s} cueF={t.cueF} dur={t.to - t.from} />
        </Sequence>
      ))}
      <Captions ch={ch} />
    </AbsoluteFill>
  );
};
