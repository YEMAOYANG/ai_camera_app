"""Persistence boundary for private homework; migrations are never run here."""
import json
from core.errors import ApiError

class HomeworkRepository:
    def __init__(self, database):
        self.database = database

    def transaction(self):
        return self.database.transaction()

    def child(self, conn, family, child, *, lock=False):
        return conn.execute('SELECT * FROM children WHERE family_id=? AND id=?'+(' FOR UPDATE' if lock else ''), (family,child)).fetchone()

    def submission(self, conn, family, identity, *, child=None, lock=False):
        row = conn.execute('SELECT * FROM homework_submissions WHERE family_id=? AND id=?',(family,identity)).fetchone()
        if row is None or row['deleted_at'] is not None or child and row['child_id'] != child:
            raise ApiError('homework_not_found','没有找到这份作业',404)
        if self.child(conn,family,row['child_id'],lock=lock) is None:
            raise ApiError('homework_not_found','没有找到这份作业',404)
        if lock:
            # Same lock order as review and unified evidence: child, then source.
            row=conn.execute('SELECT * FROM homework_submissions WHERE family_id=? AND id=? FOR UPDATE',(family,identity)).fetchone()
            if row is None or row['deleted_at'] is not None:
                raise ApiError('homework_not_found','没有找到这份作业',404)
        return row

    def pages(self, conn, identity):
        return conn.execute('SELECT * FROM homework_pages WHERE submission_id=? ORDER BY page_order,id',(identity,)).fetchall()

    def items(self, conn, identity):
        return conn.execute('SELECT i.* FROM homework_items i JOIN homework_pages p ON p.id=i.page_id WHERE i.submission_id=? ORDER BY p.page_order,i.item_order,i.id',(identity,)).fetchall()

    def asset_referenced(self, conn, key):
        """Only live pages/media and reusable successful receipts own files."""
        if key.endswith('.json'):
            actions=conn.execute('SELECT result_json FROM homework_actions WHERE result_json LIKE ?',('%'+key+'%',)).fetchall()
            for action in actions:
                value=json.loads(action['result_json'])
                if value.get('status')!='revoked' and value.get('state')!='revoked' and key in {value.get('responseJournalKey'),value.get('storageKey')}:
                    return True
            rows=conn.execute('SELECT result_json FROM homework_audio_receipts WHERE status IN (?,?) AND result_json LIKE ?',('dispatched','unknown','%'+key+'%')).fetchall()
            if any(json.loads(row['result_json']).get('savedResponseKey')==key for row in rows):
                return True
            calls=conn.execute('SELECT receipt_json FROM homework_provider_calls WHERE status!=? AND receipt_json LIKE ?',('deleted','%'+key+'%')).fetchall()
            return any(json.loads(row['receipt_json']).get('receivedResponse',{}).get('storageKey')==key
                or json.loads(row['receipt_json']).get('responseJournalKey')==key or json.loads(row['receipt_json']).get('requestJournalKey')==key for row in calls)
        if conn.execute('SELECT id FROM homework_pages WHERE storage_key=? LIMIT 1',(key,)).fetchone():
            return True
        if key.endswith('.png'):
            return False
        candidates=conn.execute('SELECT media_json FROM homework_items WHERE media_json LIKE ?',('%'+key+'%',)).fetchall()
        for row in candidates:
            media=json.loads(row['media_json']) if isinstance(row['media_json'],str) else row['media_json']
            if any(clip.get('storageKey')==key for clip in media.values()):
                return True
        receipts=conn.execute('SELECT result_json FROM homework_audio_receipts WHERE status=? AND result_json LIKE ?',('succeeded','%'+key+'%')).fetchall()
        for row in receipts:
            value=json.loads(row['result_json']) if isinstance(row['result_json'],str) else row['result_json']
            if value.get('storageKey')==key:
                return True
        return False
