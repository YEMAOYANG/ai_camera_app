import type { TextbookSubject } from "@/lib/contracts/textbooks";
import bookLayout from "./book-layout.json";

export type SchoolSubject = TextbookSubject;
export type BagPose = "closed" | "ready";
export type BagAction = "pack" | "open" | "return";
export const SCHOOL_SUBJECTS = bookLayout.map(book => book.subject as SchoolSubject);
export const RESTING_BOOK_SCALE = .9;
export const MOTION_DURATION = { pack: 2450, open: 1650, return: 2100 } as const;
export const clamp = (value: number) => Math.min(1, Math.max(0, value));
export const smooth = (value: number) => { const t = clamp(value); return t * t * t * (t * (t * 6 - 15) + 10); };
export const phase = (time: number, from: number, to: number) => smooth((time - from) / (to - from));
export const mix = (from: number, to: number, amount: number) => from + (to - from) * amount;

export function restingBook(index: number) {
  return bookLayout[index].rest;
}

// Stay in the book's own depth lane until it clears the other books. Returning
// follows the same path in reverse, with the cover closed before re-insertion.
export function bookFlight(action: "open" | "return", elapsed: number, index: number, initialLift = 0) {
  const t = clamp(elapsed / MOTION_DURATION[action]);
  const p = action === "return" ? 1 - phase(t, .06, 1) : t;
  const home = restingBook(index), lift = phase(p, 0, .30), approach = phase(p, .34, .66);
  const unfold = phase(p, .69, .90);
  return {
    x: mix(home.x, .51, approach), y: mix(home.y + mix(initialLift, .72, lift), .42, approach),
    z: mix(home.z, 3.4, approach), rx: mix(0, -.04, approach), ry: mix(0, -.18, approach),
    rz: mix(home.turn, 0, approach), scale: mix(RESTING_BOOK_SCALE, 1.1, approach),
    cover: -2.96 * unfold, backdropY: -1.9 * lift - 9.1 * approach, approach, lift,
  };
}

// Shared by the renderer and the DOM transition so their timing cannot drift.
export function motionProgress(action: BagAction, elapsed: number) {
  const progress = clamp(elapsed / MOTION_DURATION[action]);
  return {
    progress,
    opening: action === "pack" ? phase(progress, .04, .31) : 1,
    book: action === "return" ? 1 - progress : progress,
    paper: action === "open" ? phase(progress, .86, 1) : action === "return" ? 1 - phase(progress, 0, .1) : 0,
  };
}
