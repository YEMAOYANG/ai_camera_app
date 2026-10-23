import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LearningTextbookClassroom } from './learning-textbook-classroom';

const router = vi.hoisted(() => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => router }));
vi.mock('@/components/schoolbag/schoolbag-motion', () => ({ useSchoolbagMotion: () => ({ returnHome: vi.fn(), busy: false }) }));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.clearAllMocks(); });
const contentKey = 'a'.repeat(64);
const student = { id: 'student-a', childId: 'child-a', displayName: '乐乐', gradeCode: 'primary_1' };
const launch = { ok: true, contentKey, title: '课堂', editionId: 'book', revisionId: 'review-1', unitId: 'u1', learningSessionId: 'session', launchUrl: 'http://localhost:3101/mira/textbook-launch?token=test-only' };

describe('classroom entry recovery', () => {
  it('ends a stalled launch, retries explicitly, and ignores the expired response', async () => {
    vi.useFakeTimers();
    let finishExpired!: (value: Response) => void;
    const fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>(resolve => { finishExpired = resolve; }))
      .mockResolvedValueOnce(new Response(JSON.stringify(launch)));
    vi.stubGlobal('fetch', fetch);
    render(<LearningTextbookClassroom student={student} contentKey={contentKey} />);
    expect(screen.getByRole('status')).toHaveTextContent('正在翻开课本');
    await act(() => vi.advanceTimersByTimeAsync(30_000));
    expect(fetch.mock.calls[0][1].signal.aborted).toBe(true);
    expect(screen.getByRole('alert')).toHaveTextContent('打开课堂花的时间有点久');
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: '重新进入' })); });
    expect(screen.getByTitle('课堂')).toBeInTheDocument();
    await act(async () => { finishExpired(new Response('{}', { status: 401 })); });
    expect(router.replace).not.toHaveBeenCalled();
    expect(screen.getByTitle('课堂')).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledTimes(2);
  });

  it('cancels the deadline when leaving the page', async () => {
    vi.useFakeTimers();
    const fetch = vi.fn<typeof globalThis.fetch>(() => new Promise<Response>(() => {}));
    vi.stubGlobal('fetch', fetch);
    const view = render(<LearningTextbookClassroom student={student} contentKey={contentKey} />);
    view.unmount();
    expect(fetch.mock.calls[0][1]?.signal?.aborted).toBe(true);
    expect(vi.getTimerCount()).toBe(0);
  });
});

describe('rest stops the current textbook before logout', () => {
  it('sends a bounded pause immediately while logout is pending or fails', async () => {
    let finish!: (value: Response) => void;
    const fetch = vi.fn().mockResolvedValueOnce(new Response(JSON.stringify(launch)))
      .mockImplementationOnce(() => new Promise<Response>(resolve => { finish = resolve; }));
    vi.stubGlobal('fetch', fetch);
    render(<LearningTextbookClassroom student={student} contentKey={contentKey} />);
    const frame = await screen.findByTitle('课堂') as HTMLIFrameElement;
    const post = vi.spyOn(frame.contentWindow!, 'postMessage').mockImplementation(() => {});
    fireEvent.click(screen.getByRole('button', { name: '休息一下' }));
    expect(post).toHaveBeenCalledWith({ type: 'mira.textbook.pause' }, 'http://localhost:3101');
    expect(post.mock.invocationCallOrder[0]).toBeLessThan(fetch.mock.invocationCallOrder[1]);
    expect(router.replace).not.toHaveBeenCalled();
    expect(frame).toBeInTheDocument();
    finish(new Response('{}', { status: 500 }));
    expect(await screen.findByText('暂时无法锁定，请再试一次')).toBeVisible();
    expect(post).toHaveBeenCalledTimes(1); // Failure never sends resume.
    expect(router.replace).not.toHaveBeenCalled();
  });
});
