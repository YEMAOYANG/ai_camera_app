from __future__ import annotations

import uuid
from contextlib import contextmanager
from typing import Iterator

from core.database import Database, DatabaseConnection, DatabaseRow


class StudentAccessRepository:
    def __init__(self, database: Database):
        self.database = database

    @contextmanager
    def transaction(self) -> Iterator[DatabaseConnection]:
        with self.database.transaction() as conn:
            yield conn

    def create_qr_challenge(
        self,
        conn: DatabaseConnection,
        *,
        challenge_hash: str,
        verifier_hash: str,
        display_code: str,
        client_device: dict,
        client_fingerprint_hash: str,
        request_ip_hash: str | None,
        expires_at: int,
        now: int,
    ) -> DatabaseRow:
        challenge_row_id = f"student_qr_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO student_pairing_challenges(
              id, challenge_hash, verifier_hash, display_code, status,
              device_label, device_type, device_model, device_hardware,
              platform, os_version, browser_name, os_name, app_version,
              client_fingerprint_hash, request_ip_hash,
              expires_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                challenge_row_id,
                challenge_hash,
                verifier_hash,
                display_code,
                client_device["label"],
                client_device["type"],
                client_device["model"],
                client_device["hardware"],
                client_device["platform"],
                client_device["osVersion"],
                client_device["browserName"],
                client_device["osName"],
                client_device["appVersion"],
                client_fingerprint_hash,
                request_ip_hash,
                expires_at,
                now,
                now,
            ),
        )
        return conn.execute(
            "SELECT * FROM student_pairing_challenges WHERE id = ?",
            (challenge_row_id,),
        ).fetchone()

    def lock_qr_rate_bucket(
        self,
        conn: DatabaseConnection,
        *,
        bucket_kind: str,
        bucket_hash: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            INSERT INTO student_pairing_challenge_rate_buckets(
              bucket_kind, bucket_hash, created_at, updated_at
            ) VALUES (?, ?, ?, ?)
            ON DUPLICATE KEY UPDATE updated_at = VALUES(updated_at)
            """,
            (bucket_kind, bucket_hash, now, now),
        )
        conn.execute(
            """
            SELECT bucket_hash
            FROM student_pairing_challenge_rate_buckets
            WHERE bucket_kind = ? AND bucket_hash = ?
            FOR UPDATE
            """,
            (bucket_kind, bucket_hash),
        ).fetchone()

    def count_active_qr_challenges(
        self,
        conn: DatabaseConnection,
        *,
        client_fingerprint_hash: str,
        request_ip_hash: str | None,
        now: int,
    ) -> tuple[int, int]:
        fingerprint_row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM student_pairing_challenges
            WHERE client_fingerprint_hash = ?
              AND (
                (status = 'pending' AND expires_at > ?)
                OR (status = 'approved' AND approved_expires_at > ?)
              )
            """,
            (client_fingerprint_hash, now, now),
        ).fetchone()
        ip_count = 0
        if request_ip_hash:
            ip_row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM student_pairing_challenges
                WHERE request_ip_hash = ?
                  AND (
                    (status = 'pending' AND expires_at > ?)
                    OR (status = 'approved' AND approved_expires_at > ?)
                  )
                """,
                (request_ip_hash, now, now),
            ).fetchone()
            ip_count = int(ip_row["count"] if ip_row else 0)
        return int(fingerprint_row["count"] if fingerprint_row else 0), ip_count

    def count_recent_qr_challenges(
        self,
        conn: DatabaseConnection,
        *,
        client_fingerprint_hash: str,
        request_ip_hash: str | None,
        window_started_at: int,
    ) -> tuple[int, int]:
        fingerprint_row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM student_pairing_challenges
            WHERE client_fingerprint_hash = ? AND created_at >= ?
            """,
            (client_fingerprint_hash, window_started_at),
        ).fetchone()
        ip_count = 0
        if request_ip_hash:
            ip_row = conn.execute(
                """
                SELECT COUNT(*) AS count
                FROM student_pairing_challenges
                WHERE request_ip_hash = ? AND created_at >= ?
                """,
                (request_ip_hash, window_started_at),
            ).fetchone()
            ip_count = int(ip_row["count"] if ip_row else 0)
        return int(fingerprint_row["count"] if fingerprint_row else 0), ip_count

    def get_qr_challenge_for_update(
        self,
        conn: DatabaseConnection,
        *,
        challenge_hash: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM student_pairing_challenges
            WHERE challenge_hash = ?
            LIMIT 1
            FOR UPDATE
            """,
            (challenge_hash,),
        ).fetchone()

    def approve_qr_challenge(
        self,
        conn: DatabaseConnection,
        *,
        challenge_row_id: str,
        family_id: str,
        child_id: str,
        approved_by_user_id: str,
        pin_hash: str | None,
        pin_salt: str | None,
        pin_iterations: int | None,
        approved_expires_at: int,
        now: int,
    ) -> DatabaseRow | None:
        result = conn.execute(
            """
            UPDATE student_pairing_challenges
            SET status = 'approved', family_id = ?, child_id = ?,
              approved_by_user_id = ?, pin_hash = ?, pin_salt = ?,
              pin_iterations = ?, approved_expires_at = ?, approved_at = ?,
              updated_at = ?
            WHERE id = ? AND status = 'pending'
            """,
            (
                family_id,
                child_id,
                approved_by_user_id,
                pin_hash,
                pin_salt,
                pin_iterations,
                approved_expires_at,
                now,
                now,
                challenge_row_id,
            ),
        )
        if result.rowcount != 1:
            return None
        return conn.execute(
            "SELECT * FROM student_pairing_challenges WHERE id = ?",
            (challenge_row_id,),
        ).fetchone()

    def expire_qr_challenge(
        self,
        conn: DatabaseConnection,
        *,
        challenge_row_id: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE student_pairing_challenges
            SET status = 'expired', pin_hash = NULL, pin_salt = NULL,
              pin_iterations = NULL, updated_at = ?
            WHERE id = ? AND status IN ('pending', 'approved')
            """,
            (now, challenge_row_id),
        )

    def expire_due_qr_challenges(
        self,
        conn: DatabaseConnection,
        *,
        now: int,
    ) -> int:
        result = conn.execute(
            """
            UPDATE student_pairing_challenges
            SET status = 'expired', pin_hash = NULL, pin_salt = NULL,
              pin_iterations = NULL, updated_at = ?
            WHERE (status = 'pending' AND expires_at <= ?)
               OR (status = 'approved' AND approved_expires_at <= ?)
            """,
            (now, now, now),
        )
        return result.rowcount

    def delete_terminal_qr_challenges(
        self,
        conn: DatabaseConnection,
        *,
        older_than: int,
    ) -> int:
        result = conn.execute(
            """
            DELETE FROM student_pairing_challenges
            WHERE status IN ('consumed', 'expired', 'rejected')
              AND updated_at < ?
            """,
            (older_than,),
        )
        return result.rowcount

    def delete_old_qr_rate_buckets(
        self,
        conn: DatabaseConnection,
        *,
        older_than: int,
    ) -> int:
        result = conn.execute(
            """
            DELETE FROM student_pairing_challenge_rate_buckets
            WHERE updated_at < ?
            """,
            (older_than,),
        )
        return result.rowcount

    def reject_qr_challenge(
        self,
        conn: DatabaseConnection,
        *,
        challenge_row_id: str,
        family_id: str,
        child_id: str,
        rejected_by_user_id: str,
        now: int,
    ) -> DatabaseRow | None:
        result = conn.execute(
            """
            UPDATE student_pairing_challenges
            SET status = 'rejected', family_id = ?, child_id = ?,
              rejected_by_user_id = ?, rejected_at = ?,
              approved_expires_at = NULL, pin_hash = NULL, pin_salt = NULL,
              pin_iterations = NULL, updated_at = ?
            WHERE id = ? AND status IN ('pending', 'approved')
            """,
            (
                family_id,
                child_id,
                rejected_by_user_id,
                now,
                now,
                challenge_row_id,
            ),
        )
        if result.rowcount != 1:
            return None
        return conn.execute(
            "SELECT * FROM student_pairing_challenges WHERE id = ?",
            (challenge_row_id,),
        ).fetchone()

    def consume_qr_challenge(
        self,
        conn: DatabaseConnection,
        *,
        challenge_row_id: str,
        now: int,
    ) -> bool:
        result = conn.execute(
            """
            UPDATE student_pairing_challenges
            SET status = 'consumed', consumed_at = ?, updated_at = ?
            WHERE id = ? AND status = 'approved' AND consumed_at IS NULL
            """,
            (now, now, challenge_row_id),
        )
        return result.rowcount == 1

    def revoke_active_pairing_codes(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        revoked_at: int,
    ) -> None:
        conn.execute(
            """
            UPDATE student_pairing_codes
            SET revoked_at = ?
            WHERE family_id = ? AND child_id = ?
              AND consumed_at IS NULL AND revoked_at IS NULL
            """,
            (revoked_at, family_id, child_id),
        )

    def pairing_code_hash_exists(
        self,
        conn: DatabaseConnection,
        *,
        code_hash: str,
    ) -> bool:
        row = conn.execute(
            "SELECT id FROM student_pairing_codes WHERE code_hash = ? LIMIT 1",
            (code_hash,),
        ).fetchone()
        return row is not None

    def create_pairing_code(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        created_by_user_id: str,
        code_hash: str,
        pin_hash: str,
        pin_salt: str,
        pin_iterations: int,
        expires_at: int,
        created_at: int,
    ) -> DatabaseRow:
        pairing_id = f"student_pair_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO student_pairing_codes(
              id, family_id, child_id, created_by_user_id, code_hash,
              pin_hash, pin_salt, pin_iterations, expires_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                pairing_id,
                family_id,
                child_id,
                created_by_user_id,
                code_hash,
                pin_hash,
                pin_salt,
                pin_iterations,
                expires_at,
                created_at,
            ),
        )
        return conn.execute(
            "SELECT * FROM student_pairing_codes WHERE id = ?",
            (pairing_id,),
        ).fetchone()

    def get_pairing_code_for_update(
        self,
        conn: DatabaseConnection,
        *,
        code_hash: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM student_pairing_codes
            WHERE code_hash = ?
            LIMIT 1
            FOR UPDATE
            """,
            (code_hash,),
        ).fetchone()

    def consume_pairing_code(
        self,
        conn: DatabaseConnection,
        *,
        pairing_id: str,
        consumed_at: int,
    ) -> None:
        conn.execute(
            """
            UPDATE student_pairing_codes
            SET consumed_at = ?
            WHERE id = ? AND consumed_at IS NULL AND revoked_at IS NULL
            """,
            (consumed_at, pairing_id),
        )

    def get_principal_for_child(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            f"""
            SELECT * FROM student_principals
            WHERE family_id = ? AND child_id = ?
            LIMIT 1{lock}
            """,
            (family_id, child_id),
        ).fetchone()

    def create_principal(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        pin_hash: str,
        pin_salt: str,
        pin_iterations: int,
        now: int,
    ) -> DatabaseRow:
        principal_id = f"student_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO student_principals(
              id, family_id, child_id, status, pin_hash, pin_salt,
              pin_iterations, pin_updated_at, created_at, updated_at
            )
            VALUES (?, ?, ?, 'active', ?, ?, ?, ?, ?, ?)
            """,
            (
                principal_id,
                family_id,
                child_id,
                pin_hash,
                pin_salt,
                pin_iterations,
                now,
                now,
                now,
            ),
        )
        return self.get_principal(conn, principal_id=principal_id)

    def update_principal_pin(
        self,
        conn: DatabaseConnection,
        *,
        principal_id: str,
        pin_hash: str,
        pin_salt: str,
        pin_iterations: int,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            UPDATE student_principals
            SET status = 'active', pin_hash = ?, pin_salt = ?,
              pin_iterations = ?, pin_updated_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (pin_hash, pin_salt, pin_iterations, now, now, principal_id),
        )
        return self.get_principal(conn, principal_id=principal_id)

    def get_principal(
        self,
        conn: DatabaseConnection,
        *,
        principal_id: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            f"SELECT * FROM student_principals WHERE id = ? LIMIT 1{lock}",
            (principal_id,),
        ).fetchone()

    def get_student_context(
        self,
        conn: DatabaseConnection,
        *,
        principal_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT sp.*,
              c.name AS child_name,
              c.nickname AS child_nickname,
              c.grade_code AS child_grade_code,
              c.education_stage AS child_education_stage
            FROM student_principals sp
            JOIN children c
              ON c.family_id = sp.family_id AND c.id = sp.child_id
            WHERE sp.id = ?
            LIMIT 1
            """,
            (principal_id,),
        ).fetchone()

    def create_trusted_device(
        self,
        conn: DatabaseConnection,
        *,
        principal_id: str,
        family_id: str,
        child_id: str,
        device_token_hash: str,
        client_device: dict,
        expires_at: int,
        now: int,
    ) -> DatabaseRow:
        device_id = f"student_device_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO student_trusted_devices(
              id, principal_id, family_id, child_id, device_token_hash,
              device_label, device_type, device_model, device_hardware,
              platform, os_version, app_version, status, failed_pin_attempts,
              expires_at, last_active_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'trusted', 0, ?, ?, ?, ?)
            """,
            (
                device_id,
                principal_id,
                family_id,
                child_id,
                device_token_hash,
                client_device["label"],
                client_device["type"],
                client_device["model"],
                client_device["hardware"],
                client_device["platform"],
                client_device["osVersion"],
                client_device["appVersion"],
                expires_at,
                now,
                now,
                now,
            ),
        )
        return self.get_trusted_device(conn, device_id=device_id)

    def get_trusted_device(
        self,
        conn: DatabaseConnection,
        *,
        device_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM student_trusted_devices WHERE id = ? LIMIT 1",
            (device_id,),
        ).fetchone()

    def get_trusted_device_by_token_hash_for_update(
        self,
        conn: DatabaseConnection,
        *,
        device_token_hash: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM student_trusted_devices
            WHERE device_token_hash = ?
            LIMIT 1
            FOR UPDATE
            """,
            (device_token_hash,),
        ).fetchone()

    def list_owned_authorizations(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
    ) -> list[DatabaseRow]:
        return conn.execute(
            """
            SELECT
              device.id,
              device.device_label,
              device.device_type,
              device.platform,
              device.status,
              device.expires_at,
              device.last_active_at,
              device.created_at,
              device.revoked_at,
              session.id AS session_id,
              session.access_expires_at AS session_access_expires_at,
              session.refresh_expires_at AS session_refresh_expires_at,
              session.last_active_at AS session_last_active_at,
              session.created_at AS session_created_at
            FROM student_trusted_devices AS device
            LEFT JOIN student_sessions AS session
              ON session.device_id = device.id
             AND session.revoked_at IS NULL
            WHERE device.family_id = ? AND device.child_id = ?
              AND device.revoked_at IS NULL
            ORDER BY device.last_active_at DESC, device.id DESC,
              session.last_active_at DESC, session.id DESC
            """,
            (family_id, child_id),
        ).fetchall()

    def get_owned_device_for_update(
        self,
        conn: DatabaseConnection,
        *,
        family_id: str,
        child_id: str,
        device_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM student_trusted_devices
            WHERE id = ? AND family_id = ? AND child_id = ?
            LIMIT 1
            FOR UPDATE
            """,
            (device_id, family_id, child_id),
        ).fetchone()

    def revoke_trusted_device(
        self,
        conn: DatabaseConnection,
        *,
        device_id: str,
        revoked_at: int,
    ) -> bool:
        result = conn.execute(
            """
            UPDATE student_trusted_devices
            SET status = 'revoked', revoked_at = ?, updated_at = ?
            WHERE id = ? AND revoked_at IS NULL
            """,
            (revoked_at, revoked_at, device_id),
        )
        return result.rowcount == 1

    def record_failed_pin(
        self,
        conn: DatabaseConnection,
        *,
        device_id: str,
        failed_attempts: int,
        locked_until: int | None,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE student_trusted_devices
            SET failed_pin_attempts = ?, locked_until = ?, updated_at = ?
            WHERE id = ?
            """,
            (failed_attempts, locked_until, now, device_id),
        )

    def mark_device_unlocked(
        self,
        conn: DatabaseConnection,
        *,
        device_id: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE student_trusted_devices
            SET failed_pin_attempts = 0, locked_until = NULL,
              last_active_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, device_id),
        )

    def touch_device(
        self,
        conn: DatabaseConnection,
        *,
        device_id: str,
        now: int,
    ) -> None:
        conn.execute(
            """
            UPDATE student_trusted_devices
            SET last_active_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, device_id),
        )

    def create_session(
        self,
        conn: DatabaseConnection,
        *,
        principal_id: str,
        device_id: str,
        access_hash: str,
        refresh_hash: str,
        access_expires_at: int,
        refresh_expires_at: int,
        now: int,
    ) -> DatabaseRow:
        session_id = f"student_session_{uuid.uuid4().hex}"
        conn.execute(
            """
            INSERT INTO student_sessions(
              id, principal_id, device_id, access_hash, refresh_hash,
              access_expires_at, refresh_expires_at, last_active_at, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                principal_id,
                device_id,
                access_hash,
                refresh_hash,
                access_expires_at,
                refresh_expires_at,
                now,
                now,
            ),
        )
        return self.get_session(conn, session_id=session_id)

    def get_session(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            "SELECT * FROM student_sessions WHERE id = ? LIMIT 1",
            (session_id,),
        ).fetchone()

    def find_session_by_access_hash(
        self,
        conn: DatabaseConnection,
        *,
        access_hash: str,
        for_update: bool = False,
    ) -> DatabaseRow | None:
        lock = " FOR UPDATE" if for_update else ""
        return conn.execute(
            f"""
            SELECT * FROM student_sessions
            WHERE access_hash = ? AND revoked_at IS NULL
            LIMIT 1{lock}
            """,
            (access_hash,),
        ).fetchone()

    def find_session_by_refresh_hash_for_update(
        self,
        conn: DatabaseConnection,
        *,
        refresh_hash: str,
    ) -> DatabaseRow | None:
        return conn.execute(
            """
            SELECT * FROM student_sessions
            WHERE refresh_hash = ? AND revoked_at IS NULL
            LIMIT 1
            FOR UPDATE
            """,
            (refresh_hash,),
        ).fetchone()

    def rotate_session(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
        access_hash: str,
        refresh_hash: str,
        access_expires_at: int,
        refresh_expires_at: int,
        now: int,
    ) -> DatabaseRow:
        conn.execute(
            """
            UPDATE student_sessions
            SET access_hash = ?, refresh_hash = ?, access_expires_at = ?,
              refresh_expires_at = ?, last_active_at = ?, rotated_at = ?
            WHERE id = ? AND revoked_at IS NULL
            """,
            (
                access_hash,
                refresh_hash,
                access_expires_at,
                refresh_expires_at,
                now,
                now,
                session_id,
            ),
        )
        return self.get_session(conn, session_id=session_id)

    def touch_session(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
        now: int,
    ) -> None:
        conn.execute(
            "UPDATE student_sessions SET last_active_at = ? WHERE id = ?",
            (now, session_id),
        )

    def revoke_device_sessions(
        self,
        conn: DatabaseConnection,
        *,
        device_id: str,
        revoked_at: int,
    ) -> int:
        result = conn.execute(
            """
            UPDATE student_sessions
            SET revoked_at = ?
            WHERE device_id = ? AND revoked_at IS NULL
            """,
            (revoked_at, device_id),
        )
        return result.rowcount

    def revoke_principal_sessions(
        self,
        conn: DatabaseConnection,
        *,
        principal_id: str,
        revoked_at: int,
    ) -> int:
        result = conn.execute(
            """
            UPDATE student_sessions
            SET revoked_at = ?
            WHERE principal_id = ? AND revoked_at IS NULL
            """,
            (revoked_at, principal_id),
        )
        return result.rowcount

    def reset_principal_device_pin_failures(
        self,
        conn: DatabaseConnection,
        *,
        principal_id: str,
        now: int,
    ) -> int:
        result = conn.execute(
            """
            UPDATE student_trusted_devices
            SET failed_pin_attempts = 0, locked_until = NULL, updated_at = ?
            WHERE principal_id = ? AND revoked_at IS NULL
            """,
            (now, principal_id),
        )
        return result.rowcount

    def revoke_session(
        self,
        conn: DatabaseConnection,
        *,
        session_id: str,
        revoked_at: int,
    ) -> None:
        conn.execute(
            """
            UPDATE student_sessions
            SET revoked_at = ?
            WHERE id = ? AND revoked_at IS NULL
            """,
            (revoked_at, session_id),
        )
