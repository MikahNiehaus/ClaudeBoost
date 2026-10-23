import React from "react";
import { Composition } from "remotion";
import { Episode } from "./Episode";
import { FPS, H, W } from "./theme";
import { Props } from "./types";

const empty: Props = { storyboard: { title: "", scenes: [] }, map: { duration: 1, paragraphs: [] } };

export const Root: React.FC = () => (
  <Composition
    id="Episode"
    component={Episode}
    width={W}
    height={H}
    fps={FPS}
    durationInFrames={30}
    defaultProps={empty}
    calculateMetadata={({ props }) => ({ durationInFrames: Math.max(1, Math.ceil((props as Props).map.duration * FPS)) })}
  />
);
