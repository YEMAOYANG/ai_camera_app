-- Preserve existing mastery rows and isolate identically named skills by grade.
ALTER TABLE learning_mastery_states
  DROP PRIMARY KEY,
  ADD PRIMARY KEY (family_id, child_id, grade_code, node_code, subject);
