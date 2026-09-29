import type { TextbookContents } from "@/lib/contracts/textbooks";

export type TextbookLocation = { editionId?: string; revisionId?: string; unitId?: string; introductionId?: string };

export function textbookContentsPath(book: TextbookContents["book"], unitId?: string) {
  const query = new URLSearchParams({ editionId: book.editionId, revisionId: book.revisionId });
  if (unitId) query.set("unitId", unitId);
  return `/learning/textbooks?${query}`;
}

export function textbookIntroductionPath(book: TextbookContents["book"], introductionId: string) {
  return `/learning/textbooks/${encodeURIComponent(book.editionId)}/${encodeURIComponent(book.revisionId)}/intro/${encodeURIComponent(introductionId)}`;
}
