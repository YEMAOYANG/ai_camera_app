import {
  normalizeSlide,
  type PPTElement,
  type PPTImageElement,
  type PPTLineElement,
  type PPTShapeElement,
  type PPTTextElement,
  type Slide,
} from "@openmaic/dsl";

import type { ClassroomSlideBlock } from "@/lib/contracts/lesson-package";

const canvasWidth = 1000;
const canvasHeight = 562.5;

const shapePaths = {
  rectangle: "M 0 0 L 1000 0 L 1000 1000 L 0 1000 Z",
  circle: "M 500 0 A 500 500 0 1 1 499.9 0 Z",
} as const;

export function parseOpenMaicCanvas(input: unknown): Slide {
  if (!isRecord(input)) throw new Error("课堂幻灯片不是有效对象");
  const rawElements = input.elements;
  if (!Array.isArray(rawElements) || rawElements.length > 80) throw new Error("课堂幻灯片元素不完整");

  const slide: Slide = {
    id: readText(input.id, 160) || "mira-slide",
    viewportSize: readNumber(input.viewportSize, canvasWidth),
    viewportRatio: readNumber(input.viewportRatio, 0.5625),
    theme: parseTheme(input.theme),
    background: parseBackground(input.background),
    elements: rawElements.map(parseElement),
  };
  return normalizeSlide(slide);
}

export function slideFromSafeBlocks(sceneId: string, title: string, blocks: ClassroomSlideBlock[]): Slide {
  const content = blocks.filter((block) => block.type !== "shape");
  const titleElement: PPTTextElement = {
    id: `${sceneId}-title`,
    type: "text",
    left: 72,
    top: 58,
    width: 856,
    height: 92,
    rotate: 0,
    content: `<p style="font-size:46px;font-weight:800;line-height:1.22;margin:0">${escapeHtml(title)}</p>`,
    defaultFontName: "Microsoft YaHei",
    defaultColor: "#142033",
  };
  const elements: PPTElement[] = [titleElement];

  for (const [index, block] of content.entries()) {
    const column = index % 2;
    const row = Math.floor(index / 2);
    const left = 72 + column * 444;
    const top = 176 + row * 154;
    if (block.type === "text") {
      elements.push({
        id: block.id,
        type: "text",
        left,
        top,
        width: 402,
        height: 126,
        rotate: 0,
        content: `<p style="font-size:28px;font-weight:700;line-height:1.55;margin:0">${escapeHtml(block.text)}</p>`,
        defaultFontName: "Microsoft YaHei",
        defaultColor: styleColor(block.styleToken),
        fill: styleFill(block.styleToken),
      });
    } else if (block.type === "image") {
      elements.push({
        id: block.id,
        type: "image",
        left,
        top,
        width: 402,
        height: 126,
        rotate: 0,
        fixedRatio: true,
        src: block.assetRef,
      });
    }
  }

  if (content.length === 0) {
    elements.push({
      id: `${sceneId}-shape`,
      type: "shape",
      left: 340,
      top: 190,
      width: 320,
      height: 220,
      rotate: 0,
      viewBox: [1000, 1000],
      path: shapePaths.rectangle,
      fixedRatio: false,
      fill: "#eaf1ff",
      outline: { width: 3, color: "#2f6cf6" },
    });
  }

  return {
    id: sceneId,
    viewportSize: canvasWidth,
    viewportRatio: 0.5625,
    theme: miraTheme,
    background: { type: "solid", color: "#fffdf7" },
    elements,
  };
}

const miraTheme = {
  backgroundColor: "#fffdf7",
  themeColors: ["#2f6cf6", "#6d5df7", "#daf4e7", "#ffd166"],
  fontColor: "#142033",
  fontName: "Microsoft YaHei",
};

function parseTheme(input: unknown): Slide["theme"] {
  if (!isRecord(input)) return miraTheme;
  return {
    backgroundColor: readColor(input.backgroundColor, miraTheme.backgroundColor),
    themeColors: Array.isArray(input.themeColors)
      ? input.themeColors.slice(0, 12).map((value) => readColor(value, "#2f6cf6"))
      : miraTheme.themeColors,
    fontColor: readColor(input.fontColor, miraTheme.fontColor),
    fontName: readText(input.fontName, 120) || miraTheme.fontName,
  };
}

function parseBackground(input: unknown): Slide["background"] {
  if (!isRecord(input) || input.type !== "solid") return { type: "solid", color: "#fffdf7" };
  return { type: "solid", color: readColor(input.color, "#fffdf7") };
}

function parseElement(input: unknown): PPTElement {
  if (!isRecord(input)) throw new Error("课堂幻灯片包含无效元素");
  const base = {
    id: requiredText(input.id, 160),
    left: boundedNumber(input.left, 0, canvasWidth),
    top: boundedNumber(input.top, 0, canvasHeight),
    width: boundedNumber(input.width, 1, canvasWidth),
    height: boundedNumber(input.height, 1, canvasHeight),
    rotate: boundedNumber(input.rotate, -360, 360, 0),
  };
  switch (input.type) {
    case "text": {
      const element: PPTTextElement = {
        ...base,
        type: "text",
        content: sanitizeRichText(requiredText(input.content, 20_000)),
        defaultFontName: readText(input.defaultFontName, 120) || miraTheme.fontName,
        defaultColor: readColor(input.defaultColor, miraTheme.fontColor),
        fill: input.fill === undefined ? undefined : readColor(input.fill, "#ffffff"),
        lineHeight: boundedOptionalNumber(input.lineHeight, 0.7, 4),
        opacity: boundedOptionalNumber(input.opacity, 0, 1),
        vAlign: input.vAlign === "middle" || input.vAlign === "bottom" ? input.vAlign : "top",
      };
      return element;
    }
    case "shape": {
      const viewBox = isNumberPair(input.viewBox) ? input.viewBox : [1000, 1000] as [number, number];
      const element: PPTShapeElement = {
        ...base,
        type: "shape",
        viewBox,
        path: safeSvgPath(input.path) || shapePaths.rectangle,
        fixedRatio: input.fixedRatio === true,
        fill: readColor(input.fill, "#eaf1ff"),
        opacity: boundedOptionalNumber(input.opacity, 0, 1),
        outline: parseOutline(input.outline),
      };
      return element;
    }
    case "line": {
      const element: PPTLineElement = {
        id: base.id,
        type: "line",
        left: base.left,
        top: base.top,
        width: base.width,
        start: isNumberPair(input.start) ? input.start : [0, 0],
        end: isNumberPair(input.end) ? input.end : [base.width, 0],
        style: input.style === "dashed" || input.style === "dotted" ? input.style : "solid",
        color: readColor(input.color, "#2f6cf6"),
        points: ["", ""],
      };
      return element;
    }
    case "image": {
      const src = requiredText(input.src, 500);
      if (!isSafeAssetReference(src)) throw new Error("课堂图片引用不安全");
      const element: PPTImageElement = {
        ...base,
        type: "image",
        fixedRatio: input.fixedRatio !== false,
        src,
        radius: boundedOptionalNumber(input.radius, 0, 120),
      };
      return element;
    }
    default:
      throw new Error(`课堂幻灯片暂不支持 ${String(input.type)} 元素`);
  }
}

function parseOutline(input: unknown): PPTShapeElement["outline"] {
  if (!isRecord(input)) return undefined;
  return {
    color: readColor(input.color, "#2f6cf6"),
    width: boundedNumber(input.width, 0, 24, 2),
    style: input.style === "dashed" || input.style === "dotted" ? input.style : "solid",
  };
}

export function isSafeAssetReference(value: string) {
  return value.startsWith("asset:") || value.startsWith("/api/learning/assets/") || value.startsWith("data:image/");
}

export function assetReferenceUrl(value: string) {
  if (value.startsWith("asset:")) return `/api/learning/assets/${encodeURIComponent(value.slice(6))}`;
  return value;
}

function sanitizeRichText(value: string) {
  return value
    .replace(/<(?!\/?(?:p|span|strong|em|b|i|u|br|ul|ol|li)\b)[^>]*>/gi, "")
    .replace(/\son\w+\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+)/gi, "")
    .replace(/(?:javascript|data\s*:\s*text\/html)\s*:/gi, "");
}

function safeSvgPath(value: unknown) {
  if (typeof value !== "string" || value.length > 5000 || !/^[\d\s.,+\-MLHVCSQTAZmlhvcsqtaz]+$/.test(value)) return "";
  return value;
}

function styleColor(token?: string) {
  return token === "mint" ? "#397864" : token === "sun" ? "#8b651d" : token === "lilac" ? "#5443c4" : "#142033";
}

function styleFill(token?: string) {
  return token === "mint" ? "#daf4e7" : token === "sun" ? "#fff1c7" : token === "lilac" ? "#ebe5ff" : "#eaf1ff";
}

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] || character);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function readText(value: unknown, max: number) {
  return typeof value === "string" ? value.trim().slice(0, max) : "";
}

function requiredText(value: unknown, max: number) {
  const text = readText(value, max);
  if (!text) throw new Error("课堂幻灯片缺少必要文本");
  return text;
}

function readNumber(value: unknown, fallback: number) {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function boundedNumber(value: unknown, min: number, max: number, fallback = min) {
  const number = readNumber(value, fallback);
  if (number < min || number > max) throw new Error("课堂幻灯片尺寸超出范围");
  return number;
}

function boundedOptionalNumber(value: unknown, min: number, max: number) {
  return value === undefined ? undefined : boundedNumber(value, min, max);
}

function readColor(value: unknown, fallback: string) {
  return typeof value === "string" && /^(?:#[0-9a-f]{3,8}|rgba?\([\d\s,.%]+\)|transparent)$/i.test(value.trim())
    ? value.trim()
    : fallback;
}

function isNumberPair(value: unknown): value is [number, number] {
  return Array.isArray(value) && value.length === 2 && value.every((item) => typeof item === "number" && Number.isFinite(item));
}

