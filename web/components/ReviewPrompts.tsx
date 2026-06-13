export function ReviewPrompts({ prompts }: { prompts: string[] }) {
  return (
    <ul className="mt-4 space-y-2">
      {prompts.map((p, i) => (
        <li
          key={i}
          className="flex gap-3 rounded-md border border-ink-800 bg-ink-800/30 px-4 py-3 text-sm text-ink-200"
        >
          <span className="mt-0.5 font-mono text-xs text-ink-500">{String(i + 1).padStart(2, "0")}</span>
          <span>{p}</span>
        </li>
      ))}
    </ul>
  );
}
