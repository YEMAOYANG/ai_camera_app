-- Directory summary of each textbook course build.
--
-- learning_textbook_course_builds.review_json holds a build's whole review
-- record. For a few courses most of it is raw audio-audit evidence: 100-200 MB
-- of jsonb, which PostgreSQL has to decompress in full every time any part of
-- it is read. The student textbook directory needs only a few small facts from
-- that record. Reading them straight from review_json meant decompressing it
-- more than twenty times per course in one catalogue request, which exhausted
-- the database server's memory (2026-10-26).
--
-- The facts now live in their own row, computed once whenever review_json is
-- written. The builds table itself is unchanged: operator revisions store whole
-- build rows as evidence, so adding columns there would change that evidence.

-- The two values directory reads return, with the exact shape and rules of the
-- former inline query: the review record without its "release" part (NULL when
-- over 1 MiB), and the small identity and count summary of that release.
-- Anything that is not a JSON object has neither, so one damaged record cannot
-- fail the whole directory; the directory then rejects that course.
-- The stored document is read three times here and never again.
CREATE FUNCTION textbook_build_directory_projection(
  doc jsonb, OUT evidence_json jsonb, OUT summary_json jsonb
) LANGUAGE plpgsql IMMUTABLE STRICT SET search_path FROM CURRENT AS $$
DECLARE
  release jsonb;
  evidence jsonb;
BEGIN
  IF jsonb_typeof(doc) <> 'object' THEN
    RETURN;
  END IF;
  release := json_extract(doc, '$.release');
  evidence := json_remove(doc, '$.release');
  IF octet_length(evidence::text) <= 1048576 THEN
    evidence_json := evidence;
  END IF;
  summary_json := jsonb_build_object(
    'schemaVersion', json_extract(release, '$.schemaVersion'),
    'sha256', json_extract(release, '$.sha256'),
    'contentKey', json_extract(release, '$.contentKey'),
    'classroomId', json_extract(release, '$.classroomId'),
    'classroomSha256', json_extract(release, '$.classroomSha256'),
    'assessmentMode', json_extract(release, '$.assessmentMode'),
    'activityScope', json_extract(release, '$.activityScope'),
    'activityScopeType', json_type(json_extract(release, '$.activityScope')),
    'audioAudit', jsonb_build_object(
      'sha256', json_extract(release, '$.audioAudit.sha256'),
      'passed', json_extract(release, '$.audioAudit.passed'),
      'passedType', json_type(json_extract(release, '$.audioAudit.passed')),
      'segments', json_extract(release, '$.audioAudit.segments'),
      'segmentsType', json_type(json_extract(release, '$.audioAudit.segments')),
      'minSimilarityBps', json_extract(release, '$.audioAudit.minSimilarityBps')
    ),
    'mediaCount', json_length(json_extract(release, '$.media')),
    'mediaType', json_type(json_extract(release, '$.media')),
    'sceneCount', json_length(json_extract(release, '$.classroom.scenes')),
    'scenesType', json_type(json_extract(release, '$.classroom.scenes')),
    'classroomObjectId', json_extract(release, '$.classroom.id'),
    'stageId', json_extract(release, '$.classroom.stage.id')
  );
END
$$;

CREATE TABLE learning_textbook_build_directory (
  content_key varchar(64) NOT NULL,
  review_evidence_json jsonb,
  release_summary_json jsonb,
  PRIMARY KEY (content_key),
  CONSTRAINT fk_textbook_build_directory_build FOREIGN KEY (content_key)
    REFERENCES learning_textbook_course_builds (content_key) ON UPDATE CASCADE ON DELETE CASCADE
);

COMMENT ON TABLE learning_textbook_build_directory IS
  'Derived from learning_textbook_course_builds.review_json by trigger; read by the student textbook directory. Do not write to it directly.';

CREATE FUNCTION learning_textbook_build_directory_sync() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
  IF NEW.review_json IS NULL THEN
    DELETE FROM learning_textbook_build_directory WHERE content_key = NEW.content_key;
  ELSE
    INSERT INTO learning_textbook_build_directory (content_key, review_evidence_json, release_summary_json)
    SELECT NEW.content_key, projection.evidence_json, projection.summary_json
    FROM textbook_build_directory_projection(NEW.review_json) AS projection
    ON CONFLICT (content_key) DO UPDATE
      SET review_evidence_json = EXCLUDED.review_evidence_json,
          release_summary_json = EXCLUDED.release_summary_json;
  END IF;
  RETURN NULL;
END
$$;

CREATE TRIGGER learning_textbook_build_directory_sync
AFTER INSERT OR UPDATE OF review_json ON learning_textbook_course_builds
FOR EACH ROW EXECUTE FUNCTION learning_textbook_build_directory_sync();

-- Existing builds, one row at a time so memory stays bounded.
INSERT INTO learning_textbook_build_directory (content_key, review_evidence_json, release_summary_json)
SELECT build.content_key, projection.evidence_json, projection.summary_json
FROM learning_textbook_course_builds AS build
CROSS JOIN LATERAL textbook_build_directory_projection(build.review_json) AS projection
WHERE build.review_json IS NOT NULL;

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM learning_textbook_course_builds AS build
    WHERE build.review_json IS NOT NULL
      AND NOT EXISTS (SELECT 1 FROM learning_textbook_build_directory AS directory
                      WHERE directory.content_key = build.content_key)
  ) THEN
    RAISE EXCEPTION 'textbook build directory backfill is incomplete';
  END IF;
END
$$;
