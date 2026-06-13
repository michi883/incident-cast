import fs from "node:fs/promises";
import path from "node:path";
import { notFound } from "next/navigation";
import Link from "next/link";

import { Deck } from "@/lib/deck";
import { DeckView } from "@/components/DeckView";

async function loadDeck(id: string) {
  const filePath = path.join(process.cwd(), "public", "decks", `${id}.json`);
  try {
    const raw = await fs.readFile(filePath, "utf-8");
    const parsed = JSON.parse(raw);
    const result = Deck.safeParse(parsed);
    if (!result.success) {
      console.error(`Deck schema mismatch for ${id}:`, result.error);
      return null;
    }
    return result.data;
  } catch {
    return null;
  }
}

export default async function DeckPage({ params }: { params: { id: string } }) {
  const deck = await loadDeck(params.id);
  if (!deck) notFound();
  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <Link href="/" className="text-sm text-ink-400 hover:text-ink-200">
        ← all decks
      </Link>
      <DeckView deck={deck} />
    </main>
  );
}
