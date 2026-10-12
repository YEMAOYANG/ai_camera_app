import type { TextbookCatalog, TextbookContents, TextbookSubject } from "@/lib/contracts/textbooks";

export type TextbookLocation = { editionId?: string; revisionId?: string; unitId?: string; introductionId?: string; subject?: TextbookSubject };

export function textbookSubjectPath(books: TextbookCatalog["books"], subject: TextbookSubject) {
  const selected = books.find(book => book.subject === subject && book.selected);
  if (selected) return textbookContentsPath(selected);
  const published = books.filter(book => book.subject === subject && book.accessMode === "published");
  if (published.length === 1) return textbookContentsPath(published[0]);
  return published.length ? `/learning/textbooks?${new URLSearchParams({ subject })}` : null;
}

export function textbookContentsPath(book: TextbookContents["book"], unitId?: string) {
  const query = new URLSearchParams({ editionId: book.editionId, revisionId: book.revisionId });
  if (unitId) query.set("unitId", unitId);
  return `/learning/textbooks?${query}`;
}

export function textbookIntroductionPath(book: TextbookContents["book"], introductionId: string) {
  return `/learning/textbooks/${encodeURIComponent(book.editionId)}/${encodeURIComponent(book.revisionId)}/intro/${encodeURIComponent(introductionId)}`;
}
