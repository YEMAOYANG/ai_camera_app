import katex from "katex";

const mathSegments = /\$\$([\s\S]*?)\$\$|\\\[([\s\S]*?)\\\]|\\\(([\s\S]*?)\\\)|(?<!\\)\$([^$\n]+?)(?<!\\)\$/g;
const latexCommand = /\\[a-zA-Z]+/;
const unsafeCommands = /\\(?:href|url|includegraphics|htmlClass|htmlId|htmlStyle|htmlData|def|gdef|edef|xdef|newcommand|renewcommand|let|futurelet)\b/;
const fallback = "公式请看原图";

type TextPart = { kind: "text"; text: string } | { kind: "math"; formula: string; display: boolean };

function splitMath(text: string): TextPart[] {
  const parts: TextPart[] = [];
  let cursor = 0;
  // A fresh RegExp keeps parsing independent across renders.
  for (const match of text.matchAll(new RegExp(mathSegments))) {
    if (match.index > cursor) parts.push({ kind: "text", text: text.slice(cursor, match.index) });
    parts.push({ kind: "math", formula: match[1] ?? match[2] ?? match[3] ?? match[4], display: match[1] !== undefined || match[2] !== undefined });
    cursor = match.index + match[0].length;
  }
  if (cursor < text.length) parts.push({ kind: "text", text: text.slice(cursor) });
  return parts;
}

function Formula({ formula, display }: { formula: string; display: boolean }) {
  // Only KaTeX-generated markup is inserted. External URLs, injected HTML and
  // user macros are never trusted; malformed formulas retain the original image.
  if (!formula.trim() || formula.length > 2000 || unsafeCommands.test(formula)) {
    return <span className="homework-math-fallback">{fallback}</span>;
  }
  let html: string | null = null;
  try {
    html = katex.renderToString(formula, {
      displayMode: display, output: "htmlAndMathml", throwOnError: true,
      trust: false, strict: "ignore", maxExpand: 200, maxSize: 20,
    });
  } catch {
    // Parsing failure must not turn the provider's TeX into visible instructions.
  }
  return html ? <span className="homework-math-expression" data-display={display} dangerouslySetInnerHTML={{ __html: html }} />
    : <span className="homework-math-fallback">{fallback}</span>;
}

/** OCR/teacher text is presentation only: never rewrite the source or infer a
 * missing operator. In particular, bigcirc stays a circle and quad stays blank. */
export function HomeworkMathText({ text }: { text: string }) {
  const parts = splitMath(text);
  return <span className="homework-math-text">{parts.map((part, index) => part.kind === "math"
    ? <Formula key={index} formula={part.formula} display={part.display} />
    : latexCommand.test(part.text)
      ? <Formula key={index} formula={part.text} display={false} />
      : part.text)}</span>;
}
