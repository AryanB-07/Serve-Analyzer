import { useId, useState, type DragEvent } from "react";

/**
 * Drag-and-drop target backed by a real file input: the input stays in the
 * tab order (visually hidden), and the whole zone is its label, so click,
 * keyboard and drop all work.
 */
export function Dropzone({ onFile, disabled }: { onFile: (file: File) => void; disabled?: boolean }) {
  const id = useId();
  const [dragging, setDragging] = useState(false);

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file && !disabled) onFile(file);
  }

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
    >
      <input
        id={id}
        type="file"
        accept="video/mp4,video/quicktime,.mp4,.mov,.m4v"
        disabled={disabled}
        className="peer sr-only"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFile(file);
          e.target.value = "";
        }}
        data-testid="file-input"
      />
      <label
        htmlFor={id}
        className={`flex cursor-pointer flex-col items-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors peer-focus-visible:outline-2 peer-focus-visible:outline-accent peer-disabled:cursor-not-allowed peer-disabled:opacity-60 ${
          dragging ? "border-accent bg-accent/10" : "border-border bg-surface hover:border-accent/60"
        }`}
      >
        <svg viewBox="0 0 24 24" className="size-8 text-accent" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
          <path d="M12 16V4m0 0-4.5 4.5M12 4l4.5 4.5M4 16v2.5A1.5 1.5 0 0 0 5.5 20h13a1.5 1.5 0 0 0 1.5-1.5V16" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="font-medium">
          Drop your serve video here, or <span className="text-accent underline">browse</span>
        </span>
        <span className="text-sm text-ink-muted">MP4 or MOV · up to 15 s · up to 200 MB</span>
      </label>
    </div>
  );
}
