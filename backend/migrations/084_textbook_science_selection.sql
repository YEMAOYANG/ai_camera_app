-- Extend the fixed-textbook selection domain and preserve every saved selection.
-- A single ALTER keeps the existing grade/term/revision checks in force.
ALTER TABLE learning_textbook_selections
  DROP CHECK chk_textbook_selection,
  ADD CONSTRAINT chk_textbook_selection CHECK (selection_revision >= 1 AND grade_revision >= 1
    AND semester IN ('upper', 'lower') AND subject IN ('chinese', 'math', 'english', 'science'));
