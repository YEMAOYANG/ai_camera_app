import { miraWidgetProtocol } from "@/features/classroom/interactive-protocol";

const widgetCsp = [
  "default-src 'none'",
  "script-src 'unsafe-inline'",
  "style-src 'unsafe-inline'",
  "img-src data: blob:",
  "media-src data: blob:",
  "font-src data:",
  "connect-src 'none'",
  "object-src 'none'",
  "frame-src 'none'",
  "form-action 'none'",
  "base-uri 'none'",
].join("; ");

export function buildSandboxedWidgetDocument({
  sceneId,
  html,
  templateId,
  title,
  instructions,
}: {
  sceneId: string;
  html?: string;
  templateId?: "tap_choice.v1" | "match_pairs.v1" | "sort_order.v1" | "slider_lab.v1";
  title: string;
  instructions?: string;
}) {
  const content = html ? sanitizePublishedWidgetHtml(html) : builtInWidget(templateId, title, instructions);
  const bridge = `<script>
(() => {
  const protocol = ${JSON.stringify(miraWidgetProtocol)};
  const sceneId = ${JSON.stringify(sceneId)};
  const send = (kind, payload = {}) => parent.postMessage({ protocol, sceneId, kind, payload }, '*');
  window.MiraWidget = Object.freeze({
    ready: (payload) => send('ready', payload),
    progress: (payload) => send('progress', payload),
    complete: (payload) => send('complete', payload),
    error: (message) => send('error', { message: String(message || '互动暂时没有响应').slice(0, 240) }),
  });
  window.addEventListener('error', (event) => window.MiraWidget.error(event.message));
  window.addEventListener('DOMContentLoaded', () => window.MiraWidget.ready());
})();
</script>`;
  return `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><meta http-equiv="Content-Security-Policy" content="${widgetCsp}"><style>${baseWidgetCss}</style></head><body>${bridge}<main>${content}</main></body></html>`;
}

export const widgetSandboxPermissions = "allow-scripts";

function sanitizePublishedWidgetHtml(value: string) {
  const withoutDocumentShell = value
    .replace(/<!doctype[^>]*>/gi, "")
    .replace(/<\/?(?:html|head|body|base|meta|link|iframe|object|embed|form)[^>]*>/gi, "");
  return withoutDocumentShell
    .replace(/\s(?:src|href|action)\s*=\s*(?:"(?:https?:|\/\/)[^"]*"|'(?:https?:|\/\/)[^']*')/gi, "")
    .replace(/window\.(?:top|parent)\.(?!postMessage)/gi, "window.__blocked__.")
    .slice(0, 200_000);
}

function builtInWidget(
  templateId: "tap_choice.v1" | "match_pairs.v1" | "sort_order.v1" | "slider_lab.v1" | undefined,
  title: string,
  instructions?: string,
) {
  if (templateId === "slider_lab.v1") {
    return `<section class="lab"><p class="eyebrow">动手小实验</p><h1>${escapeHtml(title)}</h1><p>${escapeHtml(instructions || "拖动滑杆，观察十格框里的数量变化。")}</p><label for="amount">苹果数量 <strong id="value">5</strong></label><input id="amount" type="range" min="1" max="10" value="5"><div id="dots" class="dots" aria-live="polite"></div><button id="finish">我发现规律了</button></section><script>(()=>{const range=document.getElementById('amount');const value=document.getElementById('value');const dots=document.getElementById('dots');const render=()=>{value.textContent=range.value;dots.innerHTML='';for(let i=0;i<10;i++){const dot=document.createElement('span');dot.className=i<Number(range.value)?'on':'';dots.appendChild(dot)}window.MiraWidget.progress({value:Number(range.value)})};range.addEventListener('input',render);document.getElementById('finish').addEventListener('click',()=>window.MiraWidget.complete({completed:true,value:Number(range.value)}));render()})()</script>`;
  }
  if (templateId === "match_pairs.v1" || templateId === "sort_order.v1") {
    return `<section><p class="eyebrow">拖一拖</p><h1>${escapeHtml(title)}</h1><p>${escapeHtml(instructions || "把卡片拖到正确的位置。")}</p><div class="drag-row"><button draggable="true" id="card">学习卡</button><div id="target" class="drop-zone">拖到这里</div></div><p id="status" aria-live="polite"></p></section><script>(()=>{const card=document.getElementById('card');const target=document.getElementById('target');const status=document.getElementById('status');card.addEventListener('dragstart',e=>e.dataTransfer.setData('text/plain','card'));target.addEventListener('dragover',e=>{e.preventDefault();target.classList.add('over')});target.addEventListener('dragleave',()=>target.classList.remove('over'));target.addEventListener('drop',e=>{e.preventDefault();target.classList.remove('over');target.textContent='放好啦！';card.hidden=true;status.textContent='太棒了，配对成功！';window.MiraWidget.complete({completed:true})});card.addEventListener('click',()=>{target.textContent='放好啦！';card.hidden=true;status.textContent='太棒了，配对成功！';window.MiraWidget.complete({completed:true})})})()</script>`;
  }
  return `<section><p class="eyebrow">点一点</p><h1>${escapeHtml(title)}</h1><p>${escapeHtml(instructions || "选出你认为正确的一项。")}</p><div class="choice-grid"><button data-choice="A">A</button><button data-choice="B">B</button><button data-choice="C">C</button></div></section><script>document.querySelectorAll('[data-choice]').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('[data-choice]').forEach(item=>item.classList.remove('selected'));button.classList.add('selected');window.MiraWidget.complete({completed:true,choice:button.dataset.choice})}))</script>`;
}

const baseWidgetCss = `
:root{color-scheme:light;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:#142033;background:#fffdf7}
*{box-sizing:border-box}[hidden]{display:none!important}body{margin:0;min-width:280px;background:radial-gradient(circle at 92% 8%,#dff3ff 0,transparent 32%),linear-gradient(145deg,#fffdf7,#f5f9ff)}main{min-height:100vh;display:grid;place-items:center;padding:clamp(20px,5vw,52px)}section{width:min(760px,100%)}.eyebrow{margin:0 0 8px;color:#2459d6;font-weight:850}h1{font-size:clamp(28px,6vw,52px);line-height:1.12;margin:0 0 12px;letter-spacing:-.04em}p{font-size:clamp(16px,2.7vw,22px);line-height:1.7;color:#66758a}button,input{font:inherit}button{min-height:54px;border:2px solid #dce6f6;border-radius:18px;background:white;padding:12px 22px;font-weight:800;color:#142033;box-shadow:0 10px 24px rgba(33,54,89,.08);cursor:pointer}button:focus-visible,input:focus-visible{outline:4px solid rgba(47,108,246,.3);outline-offset:3px}.choice-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin-top:24px}.selected,#finish{border-color:#2f6cf6;background:#2f6cf6;color:white}.drag-row{display:grid;grid-template-columns:1fr 1fr;gap:20px;align-items:stretch;margin-top:28px}.drop-zone{min-height:120px;display:grid;place-items:center;border:3px dashed #9db7f5;border-radius:24px;background:#eaf1ff;color:#2459d6;font-weight:800;font-size:20px}.drop-zone.over{background:#daf4e7;border-color:#397864}.lab label{display:flex;justify-content:space-between;margin-top:26px;font-size:20px;font-weight:800}.lab input{width:100%;min-height:48px;accent-color:#2f6cf6}.dots{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin:18px 0 26px}.dots span{aspect-ratio:1;border-radius:16px;background:#e7edf5;border:2px solid #d7e0ec}.dots .on{background:#ffd166;border-color:#e6ae2d;box-shadow:inset 0 -5px 0 rgba(139,101,29,.12)}@media(max-width:520px){main{padding:18px}.drag-row{grid-template-columns:1fr}.choice-grid{gap:8px}.dots{gap:8px}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation:none!important;transition:none!important}}
`;

function escapeHtml(value: string) {
  return value.replace(/[&<>"']/g, (character) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[character] || character);
}
