"use client";

import { Eraser, Pointer, X, ZoomIn } from "lucide-react";
import { useEffect, useRef, useState, type MouseEvent } from "react";
import { Button } from "@/components/ui/button";
import type { HomeworkItem, HomeworkPage, HomeworkSubmission } from "@/lib/contracts/homework";
import { homeworkQuestionContext } from "./homework-paper-context";
import { HomeworkPaperImage, homeworkPaperCropRegion } from "./homework-paper-overview";

type Region = NonNullable<NonNullable<HomeworkItem["reviewContext"]>["region"]>;
type Mark = { id: number; x: number; y: number };
const fullPage = { x: 0, y: 0, width: 1, height: 1 };

function MarkablePicture({ submissionId, page, region, marks, onMark, onRemove, zoom = false }: {
  submissionId: string; page: HomeworkPage; region: Region | null; marks: Mark[];
  onMark: (x: number, y: number) => void; onRemove: (id: number) => void; zoom?: boolean;
}) {
  const [loaded, setLoaded] = useState(false);
  const visible = homeworkPaperCropRegion(region) ?? fullPage;
  function point(event: MouseEvent<HTMLButtonElement>) {
    const rect = event.currentTarget.getBoundingClientRect();
    // Keyboard activation places a temporary circle in the middle of this view.
    if (event.detail === 0) { onMark(visible.x + visible.width / 2, visible.y + visible.height / 2); return; }
    if (!rect.width || !rect.height) return;
    const x = (event.clientX - rect.left) / rect.width, y = (event.clientY - rect.top) / rect.height;
    if (x < 0 || x > 1 || y < 0 || y > 1) return;
    onMark(visible.x + x * visible.width, visible.y + y * visible.height);
  }
  return <div className="homework-review-picture">
    <HomeworkPaperImage submissionId={submissionId} page={page} region={region} alt={zoom ? "放大的原作业照片" : "可以点图做临时标记的原题照片"} onImageState={setLoaded} />
    {loaded && <><button type="button" className="homework-review-point-surface focus-ring" aria-label="点原图做临时标记" onClick={point} />
      {marks.filter(mark => mark.x >= visible.x && mark.x <= visible.x + visible.width && mark.y >= visible.y && mark.y <= visible.y + visible.height).map(mark => <button key={mark.id} type="button" className="homework-review-mark focus-ring" aria-label="临时标记，点一下移除" style={{ left: `${(mark.x - visible.x) / visible.width * 100}%`, top: `${(mark.y - visible.y) / visible.height * 100}%` }} onClick={() => onRemove(mark.id)}><span aria-hidden="true" /></button>)}
    </>}
  </div>;
}

/** Local pointing aid only: circles never become answers, saved evidence or AI input. */
export function HomeworkReviewExplorer({ submission, item }: { submission: HomeworkSubmission; item: HomeworkItem }) {
  const { page, region } = homeworkQuestionContext(submission, item);
  const [marks, setMarks] = useState<Mark[]>([]), [zoomOpen, setZoomOpen] = useState(false);
  const nextMark = useRef(0), dialogRef = useRef<HTMLDialogElement>(null), triggerRef = useRef<HTMLButtonElement | null>(null);
  function addMark(x: number, y: number) { const mark = { id: nextMark.current++, x, y }; setMarks(current => [...current.slice(-79), mark]); }
  function removeMark(id: number) { setMarks(current => current.filter(mark => mark.id !== id)); }
  function closeZoom() {
    if (dialogRef.current?.open && typeof dialogRef.current.close === "function") dialogRef.current.close();
    setZoomOpen(false); triggerRef.current?.focus();
  }
  useEffect(() => {
    if (!zoomOpen || !dialogRef.current) return;
    const dialog = dialogRef.current;
    if (typeof dialog.showModal === "function" && !dialog.open) dialog.showModal();
    else dialog.setAttribute("open", "");
  }, [zoomOpen]);
  return <figure className="homework-original-question homework-review-explorer" aria-label="看原图和临时圈记">
    <figcaption><span>我的原题{page && <span className="homework-source-page"> · 第 {page.order + 1} 页</span>}</span></figcaption>
    {page ? <>
      <div className="homework-review-tools"><Button size="compact" variant="secondary" onClick={event => { triggerRef.current = event.currentTarget; setZoomOpen(true); }}><ZoomIn aria-hidden="true" />放大原图</Button><Button size="compact" variant="quiet" disabled={!marks.length} onClick={() => setMarks([])}><Eraser aria-hidden="true" />清除标记</Button></div>
      <MarkablePicture submissionId={submission.id} page={page} region={region} marks={marks} onMark={addMark} onRemove={removeMark} />
      <p className="homework-review-picture-hint"><Pointer aria-hidden="true" /><span>点图做标记，再点圈圈就擦掉。</span></p>
      {zoomOpen && <dialog ref={dialogRef} className="homework-review-dialog" aria-label="放大原图和临时圈记" onCancel={event => { event.preventDefault(); closeZoom(); }} onClose={() => { setZoomOpen(false); triggerRef.current?.focus(); }}>
        <div className="homework-review-dialog-toolbar"><h3>看原图，点一点</h3><div className="homework-review-tools"><Button size="compact" variant="quiet" disabled={!marks.length} onClick={() => setMarks([])}><Eraser aria-hidden="true" />清除标记</Button><Button size="compact" variant="secondary" autoFocus onClick={closeZoom}><X aria-hidden="true" />回到题目</Button></div></div>
        <div className="homework-review-zoom-viewport"><MarkablePicture submissionId={submission.id} page={page} region={null} marks={marks} onMark={addMark} onRemove={removeMark} zoom /></div>
      </dialog>}
    </> : <p className="homework-tutor-no-photo">原作业图片暂时没打开，请回到原作业查看。</p>}
  </figure>;
}
