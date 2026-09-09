import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { SceneRail } from "@/features/classroom/classroom-chrome";
import { ClassroomQuizScene } from "@/features/classroom/quiz-scene";
import { learningTeacherProfiles } from "@/features/learning/teacher-registry";
import { classroomPackageFixture, classroomQuestionFixtures, classroomSessionFixture } from "@/test/fixtures/classroom";
import { sessionFixture } from "@/test/fixtures/learning";

describe("classroom authority gates", () => {
  it("locks future scenes until the server cursor reaches them", () => {
    render(<SceneRail scenes={classroomPackageFixture.scenes} currentSceneId={classroomPackageFixture.scenes[0].id} unlockedSceneIndex={0} open onClose={() => undefined} onSelect={() => undefined} />);
    expect(screen.getByRole("button", { name: /Mira 老师示范，完成前面场景后解锁/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /先认识 a、o、e/ })).not.toBeDisabled();
  });

  it("does not expose answer controls before the active await_interaction action", () => {
    const props = {
      session: sessionFixture,
      question: sessionFixture.currentQuestion,
      teacher: learningTeacherProfiles[0],
      guided: true,
      onSession: () => undefined,
      onQuestion: () => undefined,
      onQuizComplete: () => undefined,
    };
    const view = render(<ClassroomQuizScene {...props} enabled={false} />);
    expect(screen.getByText("先听 Mira 讲完这一小段")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /提交答案/ })).not.toBeInTheDocument();
    view.rerender(<ClassroomQuizScene {...props} enabled />);
    expect(screen.getByText(sessionFixture.currentQuestion?.prompt || "")).toBeInTheDocument();
  });

  it("only completes a controlled guided scene after a real answer result crosses its question boundary", async () => {
    const onComplete = vi.fn();
    const submitAnswer = vi.fn().mockResolvedValue({
      ok: true,
      correct: true,
      feedback: "听得很仔细，选对啦！",
      hint: null,
      canRetry: false,
      hintLevel: 0,
      nextQuestion: classroomQuestionFixtures[1],
      completed: false,
      session: { ...classroomSessionFixture, currentQuestionIndex: 1, currentQuestion: classroomQuestionFixtures[1], correctCount: 1, attemptedCount: 1 },
      report: null,
    });
    render(
      <ClassroomQuizScene
        session={classroomSessionFixture}
        question={classroomQuestionFixtures[0]}
        teacher={learningTeacherProfiles[0]}
        guided
        enabled
        questionRefs={["q2"]}
        presentation="listen_tap_choice.v1"
        gameRules={{
          goal: "听辨单韵母",
          instructions: ["先听，再选择"],
          successCriterion: "完成引导练习",
          maxAttempts: 2,
          feedbackMode: "encouraging_retry",
        }}
        submitAnswer={submitAnswer}
        onSession={() => undefined}
        onQuestion={() => undefined}
        onQuizComplete={onComplete}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /^Bo$/ }));
    expect(submitAnswer).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "选好了" }));
    await screen.findByText("听得很仔细，选对啦！");
    expect(onComplete).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /完成练习/ }));
    await waitFor(() => expect(onComplete).toHaveBeenCalledTimes(1));
  });
});
