import { memo, useEffect, useRef } from "react";
import { mountFlow } from "../flujo/animation.js";

export type Scenario = "user" | "community" | "ok" | "fail";

const LABELS: Record<Scenario, string> = {
  user: "Lo que ve el usuario",
  community: "Comunidades",
  ok: "Por dentro: swap exitoso",
  fail: "Por dentro: sin saldo",
};

/** The canvas animation with its controls. Several can share a page: each one is scoped
 * to its own root and pauses while off-screen. */
type Props = { scenarios: Scenario[]; label: string; chapters?: boolean };

// The canvas script owns the DOM inside (aria-pressed, chapters): React renders it once.
export const FlowPlayer = memo(function FlowPlayer({ scenarios, label, chapters = true }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const first = scenarios[0];
  useEffect(() => (ref.current ? mountFlow(ref.current, first) : undefined), [first]);
  return (
    <div className="flow" ref={ref}>
      <div className="flow-stage">
        <canvas data-flow="canvas" width="1280" height="720" role="img" aria-label={label} />
      </div>
      <div className="flow-controls">
        <button data-flow="play" type="button" aria-label="Reproducir">
          ▶ Reproducir
        </button>
        <button data-flow="restart" type="button">
          ↺ Reiniciar
        </button>
        {scenarios.length > 1 && (
          <div className="flow-seg" role="group" aria-label="Escenario">
            {scenarios.map((s) => (
              <button key={s} data-scen={s} type="button">
                {LABELS[s]}
              </button>
            ))}
          </div>
        )}
        <div className="flow-scrub">
          <input data-flow="scrub" type="range" min="0" max="39" step="0.01" defaultValue="0" aria-label="Posición en la animación" />
          <span className="flow-time" data-flow="time">
            0,0 s
          </span>
        </div>
      </div>
      {chapters && <div className="flow-chapters" data-flow="chapters" aria-label="Pasos" />}
    </div>
  );
}, (a, b) => a.scenarios.join() === b.scenarios.join() && a.label === b.label);
