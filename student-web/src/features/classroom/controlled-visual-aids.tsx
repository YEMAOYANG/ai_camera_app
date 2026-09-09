import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Equal,
  Plus,
} from "lucide-react";
import type { CSSProperties } from "react";

import type { ClassroomVisualAid } from "@/lib/contracts/lesson-package";

export function ControlledVisualAids({ aids }: { aids: ClassroomVisualAid[] }) {
  return (
    <div className="controlled-visual-aids" aria-label="本课数学教具">
      {aids.map((aid) => {
        if (aid.kind === "math_counters.v1") return <MathCountersAid key={aid.id} aid={aid} />;
        if (aid.kind === "number_compare.v1") return <NumberCompareAid key={aid.id} aid={aid} />;
        if (aid.kind === "place_value.v1") return <PlaceValueAid key={aid.id} aid={aid} />;
        if (aid.kind === "shape_gallery.v1") return <ShapeGalleryAid key={aid.id} aid={aid} />;
        return <PositionCompassAid key={aid.id} aid={aid} />;
      })}
    </div>
  );
}

type AidOf<Kind extends ClassroomVisualAid["kind"]> = Extract<ClassroomVisualAid, { kind: Kind }>;

function MathCountersAid({ aid }: { aid: AidOf<"math_counters.v1"> }) {
  const combine = aid.operation === "combine";
  const equation = combine
    ? `${aid.left} + ${aid.right} = ${aid.result}`
    : `${aid.left} − ${aid.right} = ${aid.result}`;
  const label = combine
    ? `${aid.left}个蓝色圆片和${aid.right}个黄色圆片合成${aid.result}个`
    : `${aid.left}个圆片去掉${aid.right}个，还剩${aid.result}个`;
  return (
    <figure className={`controlled-visual-aid math-counters-aid is-${aid.operation}`} role="img" aria-label={label}>
      <figcaption>
        <span>{combine ? "合起来" : "去掉一些"}</span>
        <strong>{equation}</strong>
      </figcaption>
      <div className="counter-equation" aria-hidden="true">
        {combine ? (
          <>
            <CounterGroup count={aid.left} tone="blue" />
            <Plus className="aid-operation-mark" />
            <CounterGroup count={aid.right} tone="sun" />
          </>
        ) : (
          <CounterGroup count={aid.left} tone="blue" removedCount={aid.right} />
        )}
        <span className="aid-flow-arrow"><ArrowRight /></span>
        <span className="aid-result-bubble">{aid.result}</span>
      </div>
      <p>{aid.caption}</p>
    </figure>
  );
}

function CounterGroup({ count, tone, removedCount = 0 }: { count: number; tone: "blue" | "sun"; removedCount?: number }) {
  return (
    <span className={`counter-group tone-${tone}`}>
      {Array.from({ length: count }, (_, index) => {
        const removed = removedCount > 0 && index >= count - removedCount;
        const style = { "--aid-item-index": index } as CSSProperties;
        return <i key={index} className={`counter-dot ${removed ? "is-removed" : ""}`} style={style} />;
      })}
    </span>
  );
}

function NumberCompareAid({ aid }: { aid: AidOf<"number_compare.v1"> }) {
  const symbol = aid.relation === "less_than" ? "<" : ">";
  return (
    <figure
      className="controlled-visual-aid number-compare-aid"
      role="img"
      aria-label={`${aid.left}${symbol}${aid.right}，${aid.caption}`}
    >
      <figcaption><span>比一比</span><strong>{aid.left} {symbol} {aid.right}</strong></figcaption>
      <div className="number-towers" aria-hidden="true">
        <NumberTower value={aid.left} tone="sun" />
        <span className="number-relation">{symbol}</span>
        <NumberTower value={aid.right} tone="blue" />
      </div>
      <p>{aid.caption}</p>
    </figure>
  );
}

function NumberTower({ value, tone }: { value: number; tone: "blue" | "sun" }) {
  const style = { "--tower-ratio": Math.max(0.18, value / 20) } as CSSProperties;
  return (
    <span className="number-tower">
      <b>{value}</b>
      <i className={`number-tower-fill tone-${tone}`} style={style} />
    </span>
  );
}

function PlaceValueAid({ aid }: { aid: AidOf<"place_value.v1"> }) {
  return (
    <figure
      className="controlled-visual-aid place-value-aid"
      role="img"
      aria-label={`${aid.value}由${aid.tens}个十和${aid.ones}个一组成，${aid.caption}`}
    >
      <figcaption><span>拆一拆</span><strong>{aid.value} = {aid.tens}个十 + {aid.ones}个一</strong></figcaption>
      <div className="place-value-model" aria-hidden="true">
        <div className="place-value-column">
          <span className="place-value-label">十位</span>
          <div className="tens-rods">
            {Array.from({ length: aid.tens }, (_, index) => (
              <i key={index}>{Array.from({ length: 10 }, (__, tick) => <span key={tick} />)}</i>
            ))}
          </div>
        </div>
        <Plus className="aid-operation-mark" />
        <div className="place-value-column">
          <span className="place-value-label">个位</span>
          <div className="ones-cubes">
            {Array.from({ length: aid.ones }, (_, index) => <i key={index} />)}
          </div>
        </div>
        <Equal className="aid-operation-mark" />
        <span className="aid-result-bubble">{aid.value}</span>
      </div>
      <p>{aid.caption}</p>
    </figure>
  );
}

function ShapeGalleryAid({ aid }: { aid: AidOf<"shape_gallery.v1"> }) {
  return (
    <figure className="controlled-visual-aid shape-gallery-aid" role="img" aria-label={`${aid.items.map((item) => item.label).join("、")}，${aid.caption}`}>
      <figcaption><span>图形家族</span><strong>看边，也看角</strong></figcaption>
      <div className="shape-gallery" aria-hidden="true">
        {aid.items.map((item) => (
          <span key={item.shape}>
            <ShapeGlyph shape={item.shape} />
            <b>{item.label}</b>
          </span>
        ))}
      </div>
      <p>{aid.caption}</p>
    </figure>
  );
}

function ShapeGlyph({ shape }: { shape: "circle" | "triangle" | "square" | "rectangle" }) {
  if (shape === "circle") return <svg viewBox="0 0 80 60"><circle cx="40" cy="30" r="22" /></svg>;
  if (shape === "triangle") return <svg viewBox="0 0 80 60"><path d="M40 7 68 53H12Z" /></svg>;
  if (shape === "square") return <svg viewBox="0 0 80 60"><rect x="18" y="8" width="44" height="44" rx="3" /></svg>;
  return <svg viewBox="0 0 80 60"><rect x="10" y="14" width="60" height="34" rx="3" /></svg>;
}

function PositionCompassAid({ aid }: { aid: AidOf<"position_compass.v1"> }) {
  return (
    <figure className="controlled-visual-aid position-compass-aid" role="img" aria-label={`以中心为参照：${aid.labels.up}、${aid.labels.down}、${aid.labels.left}、${aid.labels.right}，${aid.caption}`}>
      <figcaption><span>位置地图</span><strong>先找中心</strong></figcaption>
      <div className="position-compass" aria-hidden="true">
        <span className="position-up"><ArrowUp />{aid.labels.up}</span>
        <span className="position-left"><ArrowLeft />{aid.labels.left}</span>
        <i><span /></i>
        <span className="position-right">{aid.labels.right}<ArrowRight /></span>
        <span className="position-down"><ArrowDown />{aid.labels.down}</span>
      </div>
      <p>{aid.caption}</p>
    </figure>
  );
}
