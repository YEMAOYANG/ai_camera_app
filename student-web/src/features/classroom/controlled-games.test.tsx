import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MatchPairsScene } from "@/features/classroom/match-pairs-scene";
import { reorderSequence, SortOrderScene } from "@/features/classroom/sort-order-scene";
import type { LearningAnswerResponse, LearningQuestion } from "@/lib/contracts/learning";
import { sessionFixture } from "@/test/fixtures/learning";

const matchQuestion: LearningQuestion = {
  id: "match-1",
  type: "single_choice",
  prompt: "苹果属于哪一类？",
  skill: "词语理解",
  inputMode: "single_choice",
  choices: [{ id: "right-fruit", label: "一种水果" }, { id: "right-star", label: "发光的星球" }],
};

const sortQuestion: LearningQuestion = {
  id: "sort-1",
  type: "sequence",
  prompt: "按事情发生的顺序排一排",
  skill: "顺序表达",
  inputMode: "sequence",
  choices: [{ id: "first", label: "第一步" }, { id: "second", label: "第二步" }, { id: "third", label: "第三步" }],
};

describe("controlled classroom games", () => {
  it("builds a real clue-to-option pair and submits the existing opaque option id", async () => {
    const submitAnswer = vi.fn().mockResolvedValue(answerResult(matchQuestion));
    render(<MatchPairsScene session={{ ...sessionFixture, currentQuestion: matchQuestion }} question={matchQuestion} enabled questionRefs={[matchQuestion.id]} onSession={() => undefined} onQuestion={() => undefined} onQuizComplete={() => undefined} submitAnswer={submitAnswer} />);

    expect(screen.getByRole("button", { name: "配好啦" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /苹果属于哪一类/ }));
    fireEvent.click(screen.getByRole("button", { name: /一种水果/ }));
    fireEvent.click(screen.getByRole("button", { name: "配好啦" }));

    await waitFor(() => expect(submitAnswer).toHaveBeenCalledWith(sessionFixture.id, {
      response: {
        kind: "single_choice",
        optionId: "right-fruit",
      },
    }));
  });

  it("does not invent a match answer for a question type the evaluator does not support", () => {
    const submitAnswer = vi.fn();
    const question: LearningQuestion = { ...sortQuestion, id: "not-match" };
    render(<MatchPairsScene session={sessionFixture} question={question} enabled questionRefs={[question.id]} onSession={() => undefined} onQuestion={() => undefined} onQuizComplete={() => undefined} submitAnswer={submitAnswer} />);
    expect(screen.getByText("配对素材制作中")).toBeInTheDocument();
    expect(screen.getByText(/不会自行猜配对答案/)).toBeInTheDocument();
    expect(submitAnswer).not.toHaveBeenCalled();
  });

  it("adds, reorders and submits a sequence instead of using a renamed choice list", async () => {
    const submitAnswer = vi.fn().mockResolvedValue(answerResult(sortQuestion));
    render(<SortOrderScene session={{ ...sessionFixture, currentQuestion: sortQuestion }} question={sortQuestion} enabled questionRefs={[sortQuestion.id]} onSession={() => undefined} onQuestion={() => undefined} onQuizComplete={() => undefined} submitAnswer={submitAnswer} />);

    fireEvent.click(screen.getByRole("button", { name: /第二步/ }));
    fireEvent.click(screen.getByRole("button", { name: /第一步/ }));
    fireEvent.click(screen.getByRole("button", { name: /第三步/ }));
    const cars = screen.getAllByRole("listitem");
    fireEvent.click(within(cars[0]).getByRole("button", { name: "向后移动" }));
    fireEvent.click(screen.getByRole("button", { name: "排好啦" }));

    await waitFor(() => expect(submitAnswer).toHaveBeenCalledWith(sessionFixture.id, {
      response: { kind: "sequence", items: ["first", "second", "third"] },
    }));
  });

  it("keeps sequence movement deterministic at both boundaries", () => {
    expect(reorderSequence(["a", "b", "c"], "b", -1)).toEqual(["b", "a", "c"]);
    expect(reorderSequence(["a", "b", "c"], "a", -1)).toEqual(["a", "b", "c"]);
    expect(reorderSequence(["a", "b", "c"], "missing", 1)).toEqual(["a", "b", "c"]);
  });
});

function answerResult(question: LearningQuestion): LearningAnswerResponse {
  return {
    ok: true,
    correct: true,
    feedback: "做对啦",
    hint: null,
    canRetry: false,
    hintLevel: 0,
    nextQuestion: null,
    completed: false,
    session: { ...sessionFixture, currentQuestion: question, attemptedCount: 1, correctCount: 1 },
    report: null,
  };
}
