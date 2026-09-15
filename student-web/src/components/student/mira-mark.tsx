export function MiraMark({ compact = false }: { compact?: boolean }) {
  return <div className={`space-wordmark${compact ? " space-wordmark--compact" : ""}`} aria-label="Mira 学习空间"><strong aria-hidden="true">MIRA</strong><span>学习空间</span></div>;
}
