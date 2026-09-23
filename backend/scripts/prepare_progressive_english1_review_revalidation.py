"""Freeze the two actual settled reviews for local revalidation; no Provider/DB mutation."""
import json
from hashlib import sha256
from pathlib import Path
from core.config import AppConfig
from core.database import Database
from integrations.openmaic_formal_quality import quality_sha
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'output/progressive-preview/saved-stage-english-slot1-revision2'
NATIVE=ROOT/'openmaic-runtime/.runtime/OpenMAIC'
JOB='omformal_35329ccda267db6155963636'
AUTH='d8eca649c6be4ccb5d19b8422b1333253d76bef3ef0b555b7027efb6471f74fc'
TARGET='278de60ab4580431b84b6b8fe656a82cc25b4b8409871857a8217f172ece6983'
PREFIX=TARGET+'-predispatch-1356e0162f945f506ee93d1727a4009c4a72666fc4e11f49a9601cc25c7afd92'
REVIEW=NATIVE/'data/formal-quality-reviews/550b7f32a490d9374d2291c2de3077712d1e491819c1e771e03b0ec2aa9b382b'

def save(name,value):
 raw=(json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode();p=BASE/name
 if p.exists():assert p.read_bytes()==raw
 else:
  with p.open('xb') as f:p.chmod(0o600);f.write(raw)

def main():
 c=Database(AppConfig.from_env().DATABASE_URL).connect()
 try:
  c.execute('START TRANSACTION READ ONLY')
  rows=[dict(r) for r in c.execute('SELECT * FROM learning_budget_reservations WHERE authorization_id=? ORDER BY id',(AUTH,)).fetchall()]
  assert len(rows)==153 and all(r['state']=='settled' for r in rows)
  byid={r['id']:r for r in rows}
  provider=byid['8a7153a3449ecc8b2bdb03977ecf88bf2163be26a1dad54989aca2025496f2b5']
  visual=byid['786f6a04a91bffb01bf92b982b9c0d15bfce29bf466b2c96b3009e748724c677']
 finally:c.rollback();c.close()
 read=lambda name:json.loads((REVIEW/name).read_bytes())
 raw=(REVIEW/(PREFIX+'-provider.json')).read_bytes()
 assert sha256(raw).hexdigest()=='b820d569bc564c65ca6faaef62c06e22981cf2015e8f8d1903087b9613cbb690'
 report=json.loads(json.loads(raw)['content'])
 assert all(len(x['evidenceIds'])==len(set(x['evidenceIds'])) for x in report['dimensions']+report['objectives'])
 failure=(BASE/'visual-predispatch-complete.log').read_bytes()
 assert failure.decode().rstrip().endswith('FORMAL_QUALITY_EVIDENCE_ID_INVALID')
 evidence={'schemaVersion':'mira.english1.saved-quality-response-revalidation.v1','jobId':JOB,'authorizationId':AUTH,
  'providerResponseSha256':sha256(raw).hexdigest(),'priorAttemptsSha256':quality_sha(read('attempts.json')),
  'inputSha256':quality_sha(read(PREFIX+'-input.json')),'browserSha256':quality_sha(read(PREFIX+'-browser.json')),
  'visualSha256':quality_sha(read(PREFIX+'-visual.json')),
  'priorClaimSha256':sha256((NATIVE/'data/formal-saved-stage-recoveries'/JOB/('complete-'+TARGET+'-visual-predispatch.claim')).read_bytes()).hexdigest(),
  'failureLog':failure.decode(),'failureLogSha256':sha256(failure).hexdigest(),
  'providerReservation':provider,'visualReservation':visual,'ledgerSha256':quality_sha(rows),'settledCount':153}
 save('quality-response-revalidation-evidence.json',evidence)
 manifest=json.loads((BASE/'manifest.json').read_bytes())|{'qualityResponseRevalidationEvidencePath':'quality-response-revalidation-evidence.json'}
 save('quality-response-revalidation-manifest.json',manifest)
 print(json.dumps({'status':'prepared','evidenceSha256':quality_sha(evidence),'providerCalls':0,'databaseWrites':0}))
if __name__=='__main__':main()
