export type Scene = {
  kind: "title" | "bullets" | "flow" | "compare" | "stat" | "steps" | "term" | "graph" | "quote" | "search" | "walk" | "trace" | "code" | "chat" | "bars";
  para: number;
  w?: number;
  heading?: string;
  cues?: number[];
  [k: string]: any;
};
export type Word = { w: string; s: number; e: number };
export type Para = { index: number; spoken: boolean; start: number | null; end?: number; words: Word[] };
export type Props = { storyboard: { title: string; scenes: Scene[] }; map: { duration: number; paragraphs: Para[] } };
