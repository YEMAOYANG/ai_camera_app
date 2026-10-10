-- Extend the existing accounting boundary for private homework audio.
-- 076 created the first unnamed CHECK with this MySQL-generated name.
ALTER TABLE learning_budget_reservations
 DROP CHECK learning_budget_reservations_chk_1,
 ADD CONSTRAINT chk_learning_budget_purpose CHECK
 (purpose IN ('production', 'required_teaching', 'optional_interaction', 'homework'));
