/** Countable objects are the answer itself; text and numerals are supplementary. */
export function QuantityPicture({ count, removed = 0 }: { count: number; removed?: number }) {
  return <svg viewBox="0 0 220 185" role="img" aria-label={`${count} 个圆片${removed ? `，拿走 ${removed} 个` : ""}`}>
    <rect x="2" y="2" width="216" height="181" rx="12" fill="#f5efd9" />
    {Array.from({ length: count }, (_, i) => {
      const x = 30 + (i % 5) * 40, y = 28 + Math.floor(i / 5) * 40;
      const taken = removed > 0 && i >= count - removed;
      return <g key={i}><circle cx={x} cy={y} r="13" fill={taken ? "#ddd9cc" : "#dfad42"} stroke="#836d32" strokeWidth="1.5" />{taken && <path d={`M${x - 12} ${y + 12}l24-24`} stroke="#765b40" strokeWidth="3" />}</g>;
    })}
    {!count && <ellipse cx="110" cy="92" rx="62" ry="38" fill="none" stroke="#ad9d74" strokeWidth="3" strokeDasharray="5 7" />}
  </svg>;
}

