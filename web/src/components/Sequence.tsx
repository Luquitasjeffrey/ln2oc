/* A small sequence diagram in plain SVG, in the spirit of mermaid's sequenceDiagram
   (participants, autonumbered messages, "Note over" stage bars), without shipping mermaid.
   The same diagrams are in the README as mermaid; keep both in sync. */

export type Tone = "ln" | "btc" | "bad" | "ok" | "comm";
export type Participant = { id: string; name: string; sub?: string; tone?: Tone };
export type Step =
  | { note: string; tone?: Tone }
  | { from: string; to: string; text: string; reply?: boolean; tone?: Tone };

const COL = 200, PAD_X = 96, HEAD = 64, ROW = 40, NOTE = 34, FOOT = 26;

export function Sequence({ title, participants, steps }: { title: string; participants: Participant[]; steps: Step[] }) {
  const x = (id: string) => PAD_X + participants.findIndex((p) => p.id === id) * COL;
  const width = PAD_X * 2 + (participants.length - 1) * COL;
  let y = HEAD + 22;
  let n = 0;
  const rows = steps.map((st, i) => {
    if ("note" in st) {
      const top = y + 6;
      y += NOTE + 6;
      return (
        <g key={i} className={`sq-note ${st.tone ?? ""}`}>
          <rect x={PAD_X - 70} y={top} width={width - 2 * (PAD_X - 70)} height={NOTE - 8} rx="6" />
          <text x={width / 2} y={top + 18} textAnchor="middle">{st.note}</text>
        </g>
      );
    }
    n += 1;
    const x1 = x(st.from), x2 = x(st.to);
    const yy = y + ROW - 12;
    y += ROW;
    const cls = `sq-msg ${st.tone ?? ""}${st.reply ? " reply" : ""}`;
    if (x1 === x2) {
      return (
        <g key={i} className={cls}>
          <path d={`M${x1} ${yy - 12} h26 v14 h-22`} fill="none" />
          <path d={`M${x1 + 4} ${yy + 2} l7 -4 v8 z`} className="head" />
          <circle cx={x1 - 14} cy={yy - 6} r="9" className="num" />
          <text x={x1 - 14} y={yy - 2} textAnchor="middle" className="numt">{n}</text>
          <text x={x1 + 34} y={yy - 1} className="lbl">{st.text}</text>
        </g>
      );
    }
    const dir = x2 > x1 ? 1 : -1;
    return (
      <g key={i} className={cls}>
        <line x1={x1} y1={yy} x2={x2 - dir * 8} y2={yy} />
        <path d={`M${x2} ${yy} l${-dir * 9} -5 v10 z`} className="head" />
        <circle cx={x1 + dir * 14} cy={yy} r="9" className="num" />
        <text x={x1 + dir * 14} y={yy + 4} textAnchor="middle" className="numt">{n}</text>
        <text x={(x1 + x2) / 2 + dir * 10} y={yy - 7} textAnchor="middle" className="lbl">{st.text}</text>
      </g>
    );
  });
  const height = y + FOOT + HEAD - 20;
  const head = (top: number) =>
    participants.map((p) => (
      <g key={p.id + top} className={`sq-actor ${p.tone ?? ""}`}>
        <rect x={x(p.id) - 80} y={top} width="160" height={p.sub ? 46 : 34} rx="8" />
        <text x={x(p.id)} y={top + 21} textAnchor="middle" className="an">{p.name}</text>
        {p.sub && <text x={x(p.id)} y={top + 37} textAnchor="middle" className="as">{p.sub}</text>}
      </g>
    ));
  return (
    <figure className="sq">
      <div className="sq-scroll">
        <svg viewBox={`0 0 ${width} ${height}`} width={width} role="img" aria-label={title}>
          {participants.map((p) => (
            <line key={p.id} x1={x(p.id)} y1={HEAD - 10} x2={x(p.id)} y2={height - HEAD + 10} className="sq-life" />
          ))}
          {head(8)}
          {rows}
          {head(height - HEAD + 8)}
        </svg>
      </div>
      <figcaption>{title}</figcaption>
    </figure>
  );
}
