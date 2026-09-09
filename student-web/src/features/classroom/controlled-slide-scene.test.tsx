import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ControlledSlideScene } from "@/features/classroom/controlled-slide-scene";
import { learningTeacherProfiles } from "@/features/learning/teacher-registry";
import { classroomSceneSchema } from "@/lib/contracts/lesson-package";
import { classroomPackageFixture } from "@/test/fixtures/classroom";

describe("phonics focus slide", () => {
  it("renders distinguishable a/o/e mouth illustrations and identifies official audio", () => {
    const scene = classroomPackageFixture.scenes.find((candidate) => candidate.type === "slide" && candidate.layoutTemplate === "phonics_focus.v1");
    if (!scene || scene.type !== "slide") throw new Error("missing phonics slide fixture");
    render(<ControlledSlideScene scene={scene} teacher={learningTeacherProfiles[0]} />);
    expect(screen.getByRole("img", { name: /口型示意：a/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /口型示意：o/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /口型示意：e/ })).toBeInTheDocument();
    expect(screen.getAllByText("听标准课件音频")).toHaveLength(3);
  });

  it("renders the active controlled focus action as a real spotlight", () => {
    const scene = classroomPackageFixture.scenes.find((candidate) => candidate.type === "slide" && candidate.layoutTemplate === "phonics_focus.v1");
    if (!scene || scene.type !== "slide") throw new Error("missing phonics slide fixture");
    const { container } = render(<ControlledSlideScene scene={scene} teacher={learningTeacherProfiles[0]} focusTarget="point-2" />);
    expect(container.querySelector(".controlled-slide")).toHaveAttribute("data-spotlight-active", "true");
    expect(container.querySelector('[data-focus-id="point-2"]')).toHaveAttribute("data-spotlight-target", "true");
    expect(container.querySelector('[data-focus-id="point-1"]')).not.toHaveAttribute("data-spotlight-target");
  });

  it("renders controlled counter and place-value manipulatives as accessible teaching evidence", () => {
    const scene = classroomSceneSchema.parse({
      id: "scene-math-teach",
      type: "slide",
      order: 1,
      phaseRole: "teach",
      title: "用圆片和积木学数学",
      layoutTemplate: "concept_focus.v1",
      blocks: [
        { id: "teacher", type: "text", text: "先动手看一看，再说出你发现的关系。", styleToken: "teacher" },
        { id: "point", type: "text", text: "把两部分合起来", styleToken: "key_point" },
      ],
      templateData: {
        visualAids: [
          {
            id: "visual-add",
            kind: "math_counters.v1",
            operation: "combine",
            left: 8,
            right: 4,
            result: 12,
            caption: "把两部分合起来，就是加法。",
          },
          {
            id: "visual-place-value",
            kind: "place_value.v1",
            value: 13,
            tens: 1,
            ones: 3,
            caption: "一捆表示一个十，单个小方块表示一个一。",
          },
        ],
      },
      actions: [],
    });
    if (scene.type !== "slide") throw new Error("missing controlled math slide");
    render(<ControlledSlideScene scene={scene} teacher={learningTeacherProfiles[0]} />);
    expect(screen.getByRole("img", { name: "8个蓝色圆片和4个黄色圆片合成12个" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /13由1个十和3个一组成/ })).toBeInTheDocument();
    expect(screen.getByText("8 + 4 = 12")).toBeInTheDocument();
    expect(screen.getByText("13 = 1个十 + 3个一")).toBeInTheDocument();
  });

  it("renders the complete shape family and the four-way position reference", () => {
    const scene = classroomSceneSchema.parse({
      id: "scene-shape-teach",
      type: "slide",
      order: 1,
      phaseRole: "teach",
      title: "认识图形和位置",
      layoutTemplate: "concept_focus.v1",
      blocks: [{ id: "teacher", type: "text", text: "先看形状，再找中心。", styleToken: "teacher" }],
      templateData: {
        visualAids: [
          {
            id: "visual-shapes",
            kind: "shape_gallery.v1",
            items: [
              { shape: "circle", label: "圆形" },
              { shape: "triangle", label: "三角形" },
              { shape: "square", label: "正方形" },
              { shape: "rectangle", label: "长方形" },
            ],
            caption: "看边和角的特点，认出常见平面图形。",
          },
          {
            id: "visual-position",
            kind: "position_compass.v1",
            labels: { up: "上", down: "下", left: "左", right: "右" },
            caption: "先找观察中心，再说清上下左右。",
          },
        ],
      },
      actions: [],
    });
    if (scene.type !== "slide") throw new Error("missing controlled shape slide");
    render(<ControlledSlideScene scene={scene} teacher={learningTeacherProfiles[0]} />);
    expect(screen.getByRole("img", { name: /圆形、三角形、正方形、长方形/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /以中心为参照：上、下、左、右/ })).toBeInTheDocument();
  });
});
