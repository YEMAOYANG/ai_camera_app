import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { HomeworkMathText } from "./homework-math-text";

afterEach(cleanup);

describe("photographed homework formula presentation", () => {
  it("renders the photographed operator circle and all three boxes without inferring an operator or an answer", () => {
    const text = String.raw`$\boxed{4} \bigcirc \boxed{1} = \boxed{\quad}$`;
    const { container } = render(<HomeworkMathText text={text} />);
    const visible = container.querySelector(".katex-html")!;
    expect(visible.querySelectorAll(".fbox")).toHaveLength(3);
    expect(visible.textContent).toMatch(/[○◯]/);
    expect(visible.textContent).toContain("4");
    expect(visible.textContent).toContain("1");
    expect(visible.textContent).not.toMatch(/boxed|bigcirc|quad|[+×]/);
    expect(visible.querySelectorAll(".fbox")[2].textContent?.trim()).toBe("");
    expect(container.querySelector("math")).not.toBeNull();
  });

  it("preserves Chinese prose, multiple inline formulas and fractional structure", () => {
    const { container } = render(<HomeworkMathText text={String.raw`先看 $\frac{1}{2}$，再看 \(3+2\)。`} />);
    expect(container.querySelectorAll(".katex-html")).toHaveLength(2);
    expect(container.querySelector(".mfrac")).not.toBeNull();
    expect(container.textContent).toContain("先看");
    expect(container.textContent).toContain("，再看");
  });

  it("handles display and undelimited OCR formulas", () => {
    const { container } = render(<HomeworkMathText text={String.raw`$$2^3=8$$ 和 \boxed{\quad}`} />);
    expect(container.querySelector('[data-display="true"]')).not.toBeNull();
    expect(container.querySelectorAll(".katex-html")).toHaveLength(2);
    expect(container.querySelector(".homework-math-fallback")).toBeNull();
  });

  it.each([String.raw`$\unknown{4}$`, String.raw`$\frac{1}{$`, String.raw`$\boxed{4`])("uses the original-picture fallback for malformed OCR %s", text => {
    const { container } = render(<HomeworkMathText text={text} />);
    expect(container.textContent).toBe("公式请看原图");
    expect(container.querySelector(".katex-error")).toBeNull();
  });

  it.each([String.raw`$\href{https://example.com}{4}$`, String.raw`$\includegraphics{https://example.com/a.png}$`, String.raw`$\htmlStyle{color:red}{4}$`, String.raw`$\def\x{\x}\x$`])("does not trust OCR links, HTML, images or macros %s", text => {
    const { container } = render(<HomeworkMathText text={text} />);
    expect(container.textContent).toBe("公式请看原图");
    expect(container.querySelector("a,img,script")).toBeNull();
  });

  it("escapes plain OCR HTML and leaves ordinary prose and unpaired currency untouched", () => {
    const text = '买一本书 $5。<img src=x onerror="alert(1)">';
    const { container } = render(<HomeworkMathText text={text} />);
    expect(container.textContent).toBe(text);
    expect(container.querySelector("img,script")).toBeNull();
  });
});
