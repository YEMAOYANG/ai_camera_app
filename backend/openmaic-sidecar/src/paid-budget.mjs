import { createHash } from 'node:crypto';
const sha = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export function paidBudgetBinding() {
  const raw = process.env.MIRA_PAID_BUDGET_BINDING;
  if (!raw) return null;
  const binding = JSON.parse(raw);
  if (!binding || Object.keys(binding).sort().join(',') !== 'authorizationId,required,schemaVersion'
      || binding.schemaVersion !== 'mira.learning.paid-budget-binding.v1' || binding.required !== true
      || !/^[a-f0-9]{64}$/.test(binding.authorizationId)) throw new Error('paid budget binding invalid');
  return binding;
}
export function paidBudgetHeaders() {
  const binding = paidBudgetBinding();
  return binding ? {'X-Mira-Paid-Budget-Required':'1','X-Mira-Paid-Budget-Authorization':binding.authorizationId} : {};
}
export async function beginPaidProviderDispatch(provider, requestBody, requestId, fetchImpl = fetch) {
  const binding = paidBudgetBinding();
  if (!binding) return null;
  const base = process.env.MIRA_PAID_BUDGET_BACKEND_URL;
  const token = process.env.MIRA_PAID_BUDGET_INTERNAL_TOKEN;
  if (!base || !token) throw new Error('paid budget service unavailable');
  async function call(operation, body) {
    const response = await fetchImpl(new URL(`/internal/learning/budget/${operation}`,base),{
      method:'POST',redirect:'error',signal:AbortSignal.timeout(15000),
      headers:{'Content-Type':'application/json','X-Mira-Internal-Token':token,'X-Mira-Internal-Source':'openmaic-runtime-gateway'},
      body:JSON.stringify(body),
    });
    const payload=await response.json();
    if(!response.ok || !payload.ok || !payload.budget)throw new Error('paid budget request rejected');
    return payload.budget;
  }
  const {authorizationId}=binding;
  const context=await call('context',{authorizationId});
  const selected=Object.entries(context.prices).filter(([,p])=>p.provider===provider.name && p.model===provider.model);
  if(selected.length!==1)throw new Error('paid budget price not authorized');
  const [priceKey,price]=selected[0];
  const measured={calls:1,input_tokens:Buffer.byteLength(JSON.stringify(requestBody.messages))+4096,output_tokens:provider.maxTokens};
  if(Object.keys(measured).some(unit=>!price.allowedUnits.includes(unit) || !Number.isSafeInteger(measured[unit]) || measured[unit]<0 || measured[unit]>price.perCallMax[unit]))
    throw new Error('paid budget token limit');
  const maxUnits=Object.fromEntries(price.allowedUnits.map(unit=>[unit,measured[unit]??price.perCallMax[unit]]));
  const requestSha256=sha(requestBody);
  // Phase requestId is frozen in the DB; another body cannot become a retry.
  const dispatchId=`sidecar:${sha([authorizationId,requestId??requestSha256])}`;
  const reservation=await call('reserve',{authorizationId,dispatchId,requestSha256,priceKey,maxUnits});
  const identity={authorizationId,reservationId:reservation.reservationId};
  const permission=await call('dispatch',{...identity,requestSha256});
  if(permission.dispatchAllowed!==true)throw new Error('paid budget dispatch already claimed');
  let finished=false;
  const unknown=async()=>{
    if(finished)return;finished=true;
    await call('unknown',{...identity,reasonCode:'provider_result_unknown'}).catch(()=>{});
  };
  return {unknown,async settle(usage) {
    if(finished)return;
    const actual={calls:1,input_tokens:usage.inputTokens,output_tokens:usage.outputTokens};
    if(price.allowedUnits.some(unit=>!Number.isSafeInteger(actual[unit]) || actual[unit]<0))return unknown();
    await call('settle',{...identity,actualUnits:actual,providerRequestId:usage.providerRequestIdHash??null,evidenceSha256:sha(actual)});
    finished=true;
  }};
}
