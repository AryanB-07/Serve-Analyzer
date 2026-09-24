import { CameraDiagram } from "./CameraDiagram";
import { MAX_DURATION_S } from "./validateVideo";

const TIPS: [title: string, detail: string][] = [
  ["Film side-on", "Put the camera at right angles to the direction you serve, so it sees the side of your body."],
  ["5–10 m away, at hip height", "Use a tripod or lean the phone on the fence so the shot is steady."],
  ["Whole body in frame", "Leave room above your head for the racket at full reach, and keep your feet in shot."],
  [`One serve, ${MAX_DURATION_S} s max`, "Trim the clip to just before the toss until just after contact."],
  ["30 fps or more, good light", "60 fps or slow-motion catches the fast part of the swing much better."],
];

export function FilmingGuide() {
  return (
    <section id="filming-guide" aria-labelledby="filming-guide-heading" className="scroll-mt-20 space-y-4 rounded-xl border border-border bg-surface p-5">
      <h2 id="filming-guide-heading" className="text-lg font-semibold">How to film your serve</h2>
      <CameraDiagram />
      <ol className="space-y-3">
        {TIPS.map(([title, detail], i) => (
          <li key={title} className="grid grid-cols-[auto_1fr] gap-x-3">
            <span className="tabular grid size-6 place-items-center rounded-full bg-surface-2 text-xs font-semibold" aria-hidden>
              {i + 1}
            </span>
            <div>
              <p className="text-sm font-medium">{title}</p>
              <p className="text-sm text-ink-muted">{detail}</p>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
