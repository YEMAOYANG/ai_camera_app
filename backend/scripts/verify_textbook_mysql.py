"""Check textbook, review, homework migrations and concurrent reservations on isolated MySQL.

Starts its own server with networking disabled and a fresh temporary data dir.
Never reads AppConfig, .env or an existing database. Requires a local mysqld.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymysql
from pymysql.cursors import DictCursor
from content.textbook_catalog import generation_brief
from core.database import DatabaseConnection
from core.errors import ApiError
from repositories.textbook_repository import TextbookRepository
from services.textbook_learning_service import TextbookLearningService
from services.textbook_preview_service import TextbookPreviewService
from types import SimpleNamespace
from unittest.mock import Mock


class SocketDatabase:
    def __init__(self, socket):
        self.socket = socket

    @contextmanager
    def transaction(self):
        raw = pymysql.connect(unix_socket=self.socket, user="root", database="textbook_isolated_test", cursorclass=DictCursor, autocommit=False)
        conn = DatabaseConnection(raw, dialect="mysql")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def verify(socket):
    raw = pymysql.connect(unix_socket=socket, user="root", autocommit=True)
    with raw.cursor() as cursor:
        cursor.execute("CREATE DATABASE textbook_isolated_test CHARACTER SET utf8mb4 COLLATE utf8mb4_bin")
    raw.close()
    db = SocketDatabase(socket)
    repo = TextbookRepository(db)
    service = TextbookLearningService(repo)
    with db.transaction() as conn:
        conn.executescript((ROOT / "migrations/082_fixed_textbook_learning.sql").read_text())
        conn.executescript((ROOT / "migrations/083_textbook_course_previews.sql").read_text())
        conn.executescript((ROOT / "migrations/087_learning_course_reuse.sql").read_text())
        conn.executescript((ROOT / "migrations/085_learning_reviews.sql").read_text())
        conn.executescript((ROOT / "migrations/086_homework_analysis.sql").read_text())
        conn.executescript((ROOT / "migrations/076_learning_paid_budget.sql").read_text())
        conn.executescript((ROOT / "migrations/088_homework_paid_budget.sql").read_text())
        conn.execute("CREATE TABLE children (id VARCHAR(128) PRIMARY KEY, family_id VARCHAR(128), grade_code VARCHAR(32), grade_selection_revision INT)")
        conn.execute("INSERT INTO children VALUES ('isolated-child','isolated-family','primary_1',1)")
    m = json.loads((ROOT / "content/textbooks/pep-chinese-g1-upper.preview.v1.json").read_text())
    m["rightsReview"] = {"status": "cleared", "basis": "Synthetic disposable database test only"}
    m["units"][0]["lessons"][0]["brief"]["status"] = "approved"
    with ThreadPoolExecutor(max_workers=4) as pool:
        imported = list(pool.map(lambda _: service.import_manifest(m), range(4)))
    assert sum(r["created"] for r in imported) == 1, imported
    query = {"editionId": m["editionId"], "alignmentRevisionId": m["revisionId"], "nodeId": "u1-l1"}
    with ThreadPoolExecutor(max_workers=4) as pool:
        prepared = list(pool.map(lambda _: service.prepare(query), range(4)))
    assert sum(r["created"] for r in prepared) == 1, prepared
    assert len({r["contentKey"] for r in prepared}) == 1

    def select(_):
        try:
            with db.transaction() as conn:
                child = repo.child(conn, "isolated-family", "isolated-child", lock=True)
                return repo.select(conn, child=child, manifest=m, year=2026, semester="upper", expected_revision=0,
                                   current_node=None, confirmed_by="isolated-parent", now=1)
        except ApiError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=4) as pool:
        selected = list(pool.map(select, range(4)))
    assert selected.count(1) == 1 and selected.count("textbook_selection_changed") == 3, selected
    with db.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) AS n FROM learning_textbook_course_builds").fetchone()["n"] == 1
        assert conn.execute("SELECT COUNT(*) AS n FROM learning_textbook_selection_events").fetchone()["n"] == 1
    try:
        with db.transaction() as conn:
            conn.execute("UPDATE learning_textbook_course_builds SET status='published'")
        raise AssertionError("MySQL accepted publication without course/hash/review")
    except pymysql.err.OperationalError as exc:
        assert exc.args[0] == 3819, exc
    assert prepared[0]["contentKey"] == generation_brief(m, "u1-l1")["contentKey"]
    preview_manifest = json.loads((ROOT / "content/textbooks/revisions/pep-chinese-g1-upper.preview.v2.json").read_text())
    service.import_manifest(preview_manifest)
    job = SimpleNamespace(job_id="isolated-preview-job", status="running", step="generating_scenes", progress=30, scenes_count=None, classroom_id=None)
    runtime = Mock(base_url="http://127.0.0.1:3100")
    runtime.start_generation.return_value = job
    runtime.get_generation_job.return_value = job
    previews = TextbookPreviewService(repo, runtime)
    with ThreadPoolExecutor(max_workers=4) as pool:
        reservations = list(pool.map(lambda _: previews.prepare(preview_manifest["editionId"], preview_manifest["revisionId"], "u1-l1"), range(4)))
    assert len({r["previewKey"] for r in reservations}) == 1
    preview_key = reservations[0]["previewKey"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: previews.start(preview_key), range(4)))
    assert runtime.start_generation.call_count == 1
    assert previews.poll(preview_key)["runtimeJobId"] == job.job_id
    # Exercise the newly added review tables on real InnoDB transactions, with
    # synthetic content only. No provider, camera or existing data is involved.
    from services.learning_evidence_service import record_answer, digest
    from services.learning_review_service import LearningReviewService
    now = int(datetime(2026, 10, 3, 9, tzinfo=ZoneInfo("Asia/Shanghai")).timestamp() * 1000)
    question = {"id": "isolated-question", "version": "1", "subject": "math", "gradeCode": "primary_1",
                "knowledgeId": "isolated:addition", "knowledgeLabel": "Synthetic addition",
                "courseId": "isolated-course", "courseTitle": "Synthetic course", "courseVersion": "1",
                "renderer": "picture_choices", "prompt": "Synthetic verification only", "visual": {},
                "options": [], "correctAnswer": "A", "estimatedSeconds": 60, "private": False,
                "promptAudioAsset": "fixture.wav", "hintAudioAssets": [], "explanationAudioAsset": "fixture.wav"}
    question["fingerprint"] = digest(question)
    def save_answer(_):
        with db.transaction() as conn:
            return record_answer(conn, family_id="isolated-family", child_id="isolated-child",
                                 source_kind="classroom", source_id="isolated-session", event_key="same-answer",
                                 question=question, answer="B", correct=False, occurred_at=now-1000,
                                 independent=True, hint_used=False, adult_help=False)
    with ThreadPoolExecutor(max_workers=4) as pool:
        evidence = list(pool.map(save_answer, range(4)))
    assert len({row["id"] for row in evidence}) == 1
    with db.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) n FROM learning_answer_events").fetchone()["n"] == 1
        names = "id,family_id,child_id,title,description,type,status,scheduled_date,scheduled_start,scheduled_end,schedule_type,start_at,due_at,priority,reward_points,requires_parent_confirmation,created_by,reminder_minutes_before,reminder_status,timezone,learning_assignment_key,learning_slot,created_at,updated_at,next_reminder_at,started_at,completed_at,ended_at,completion_source,evidence_summary".split(",")
        conn.execute("CREATE TABLE tasks (" + ",".join(name + (" VARCHAR(255) PRIMARY KEY" if name == "id" else " TEXT") for name in names) + ")")
    review_service = LearningReviewService(db, auth_service=None, student_auth_service=None,
                                         question_pool=lambda conn, child: ([dict(question)], []), clock=lambda: now)
    def prepare_week(_):
        with db.transaction() as conn:
            child = review_service.repository.child(conn, "isolated-family", "isolated-child")
            return review_service.ensure_week(conn, child, now)
    with ThreadPoolExecutor(max_workers=4) as pool:
        reviews = list(pool.map(prepare_week, range(4)))
    assert len({row["id"] for row in reviews}) == 1
    with db.transaction() as conn:
        assert conn.execute("SELECT COUNT(*) n FROM learning_review_runs").fetchone()["n"] == 1
        assert conn.execute("SELECT COUNT(*) n FROM tasks").fetchone()["n"] == 1
    return {"migration": "passed", "migrationFiles": ["076", "082", "083", "085", "086", "087", "088"], "concurrentImports": 4, "uniqueImportedRevision": 1,
            "concurrentPreparations": 4, "uniqueBuild": 1, "concurrentSelections": 4,
            "successfulSelections": 1, "publicationCheckConstraint": "passed", "existingDatabaseTouched": False,
            "concurrentPreviewStarts": 4, "previewDispatches": runtime.start_generation.call_count,
            "concurrentEvidenceWrites": 4, "uniqueAnswerEvent": 1,
            "concurrentWeeklySchedules": 4, "uniqueWeeklyReview": 1, "uniqueReviewTask": 1,
            "realProviderDispatched": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mysqld", default=shutil.which("mysqld"))
    args = parser.parse_args()
    if not args.mysqld:
        parser.error("Pass --mysqld /absolute/path/to/mysqld")
    with tempfile.TemporaryDirectory(prefix="mira-textbook-mysql-", dir="/tmp") as temp:
        root = Path(temp)
        log = root / "server.log"
        data = root / "data"
        socket = str(root / "mysql.sock")
        with log.open("w+") as output:
            try:
                subprocess.run([args.mysqld, "--no-defaults", "--initialize-insecure", f"--datadir={data}"], stdout=output, stderr=subprocess.STDOUT, check=True, timeout=60)
            except subprocess.CalledProcessError:
                output.flush()
                print(log.read_text()[-1800:], file=sys.stderr)
                raise
            process = subprocess.Popen([args.mysqld, "--no-defaults", f"--datadir={data}", f"--socket={socket}", "--skip-networking", "--mysqlx=OFF", f"--pid-file={root / 'mysql.pid'}"], stdout=output, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 25
                while not Path(socket).exists():
                    if process.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("Disposable MySQL did not start")
                    time.sleep(0.1)
                print(json.dumps(verify(socket), indent=2))
            except Exception:
                output.flush()
                print(log.read_text()[-1800:], file=sys.stderr)
                raise
            finally:
                process.terminate()
                try:
                    process.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=5)


if __name__ == "__main__":
    main()
