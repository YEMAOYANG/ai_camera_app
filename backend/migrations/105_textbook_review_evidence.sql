-- Audio evidence moved out of oversized published review records.
--
-- learning_textbook_course_builds.review_json holds a build's whole review
-- record. The builds that reuse ASR provenance (audio-audit v3 and v4) embed
-- every recording three to eleven times inside release.audioAudit.literalAudit
-- and repeat the same large plan objects in every origin: 100-200 MB of jsonb
-- per record, of which only about 30-45 MB is distinct audio.
--
-- backend/content/textbook_review_evidence.py moves those bytes here, once
-- each and keyed by their own SHA-256, and leaves a reference in the record.
-- Restoring them gives back the original value exactly, so no sealed digest of
-- a published course changes. The database itself guarantees that an item is
-- only ever the bytes its key names: the key must equal the hash of the body,
-- and rows cannot be updated. Nothing in this migration changes an existing row.

CREATE TABLE learning_textbook_review_evidence (
  sha256 varchar(64) NOT NULL,
  body bytea NOT NULL,
  byte_length integer NOT NULL,
  created_at bigint NOT NULL,
  PRIMARY KEY (sha256),
  CONSTRAINT chk_textbook_review_evidence CHECK (
    byte_length = octet_length(body) AND sha256 = encode(sha256(body), 'hex'))
);

COMMENT ON TABLE learning_textbook_review_evidence IS
  'Content-addressed evidence split out of learning_textbook_course_builds.review_json: recording bytes and shared canonical JSON objects, read as one or the other by the reference that points at them. Written by scripts/split_textbook_review_evidence.py; read when a release is validated.';

CREATE FUNCTION learning_textbook_review_evidence_immutable() RETURNS trigger
LANGUAGE plpgsql SET search_path FROM CURRENT AS $$
BEGIN
  RAISE EXCEPTION 'learning_textbook_review_evidence rows are immutable (sha256 %)', OLD.sha256;
END
$$;

CREATE TRIGGER learning_textbook_review_evidence_immutable
BEFORE UPDATE ON learning_textbook_review_evidence
FOR EACH ROW EXECUTE FUNCTION learning_textbook_review_evidence_immutable();
