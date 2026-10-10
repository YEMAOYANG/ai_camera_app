#!/usr/bin/env python3
"""Read-only preflight, or enqueue the one human-authorized image-v2 recovery.

This exact local operation never calls a Provider or starts a worker. With the
explicit execution flag, the normal worker may claim the atomically queued job
immediately. Repeating the command returns the same grant/job, never a new one.
No credentials, private image contents, or recognition text are printed.
"""
from __future__ import annotations

import argparse
from contextlib import redirect_stderr,redirect_stdout
import io
import json
from pathlib import Path
import sys
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from flask import Flask
from core.config import AppConfig
from core.database import Database
from core.errors import ApiError
from services.service_factory import homework_service

AUTHORIZED_SCOPE={
    'phone':'13860469696',
    'familyId':'fam_0f796fdf858543069216ab17b523f8c3',
    'childId':'child_6d57c9cfd92f4b29b2438cf6d9f42f51',
    'submissionId':'hw_7e7240cf0a3d483a943c91681b671d60',
    'expectedRevision':4,
    'unknownCallId':'hwcall_7e1ee40131c48cb899ba87fd31dd18f8abb6b6c0cd03ece19597f5ce',
}


def parser():
    result=argparse.ArgumentParser(description=__doc__)
    result.add_argument('--phone',required=True,choices=[AUTHORIZED_SCOPE['phone']])
    result.add_argument('--child-id',required=True,choices=[AUTHORIZED_SCOPE['childId']])
    result.add_argument('--submission-id',required=True,choices=[AUTHORIZED_SCOPE['submissionId']])
    result.add_argument('--revision',type=int,required=True,choices=[AUTHORIZED_SCOPE['expectedRevision']])
    result.add_argument('--unknown-call-id',required=True,choices=[AUTHORIZED_SCOPE['unknownCallId']])
    result.add_argument('--execute-authorized-reanalysis',action='store_true',
        help='Record the existing human approval and enqueue exactly one new image-v2 request')
    return result


def validate_config(config):
    target=urlparse(config['DATABASE_URL'])
    if (config.get('APP_ENV')!='development' or target.scheme.split('+',1)[0]!='mysql'
            or target.hostname not in {'127.0.0.1','localhost'} or target.path!='/ai_camera_app_dev'):
        raise ValueError('exact_local_development_database_required')
    # Do not override the worker/audio flags or use a synthetic submission.
    if not config.get('HOMEWORK_ANALYSIS_ENABLED'):
        raise ValueError('homework_analysis_disabled')


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        with redirect_stdout(io.StringIO()),redirect_stderr(io.StringIO()):
            app=Flask('mira-authorized-homework-recovery')
            app.config.update(AppConfig.from_env().to_flask_config())
            validate_config(app.config)
            prompt_root=Path(app.config['PROMPT_ROOT'])
            if not prompt_root.is_absolute():
                app.config['PROMPT_ROOT']=str((ROOT/prompt_root).resolve())
            database=Database(app.config['DATABASE_URL'])
            with app.app_context():
                service=homework_service()
                if args.execute_authorized_reanalysis:
                    with database.transaction() as conn:
                        result=service.authorize_recognition_repair(conn,dict(AUTHORIZED_SCOPE),
                            execute=True,approval_text='允许重新分析一次')
                else:
                    conn=database.connect()
                    try:
                        conn.execute('START TRANSACTION READ ONLY')
                        result=service.authorize_recognition_repair(conn,dict(AUTHORIZED_SCOPE))
                    finally:
                        conn.rollback()
                        conn.close()
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except ApiError as error:
        print(json.dumps({'ok':False,'error':error.code},ensure_ascii=False))
        return 1
    except Exception:
        # SQL/configuration exception strings can contain connection material.
        print(json.dumps({'ok':False,'error':'homework_repair_preflight_failed'}))
        return 1


if __name__=='__main__':
    raise SystemExit(main())
