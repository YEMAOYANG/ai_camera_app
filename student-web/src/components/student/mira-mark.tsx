export function MiraMark({ compact = false }: { compact?: boolean }) {
  return <div className={compact ? "mira-wordmark mira-wordmark--compact" : "mira-wordmark"} aria-label="Mira 学习空间"><strong aria-hidden="true">MIRA</strong><span>学习空间</span></div>;
}
