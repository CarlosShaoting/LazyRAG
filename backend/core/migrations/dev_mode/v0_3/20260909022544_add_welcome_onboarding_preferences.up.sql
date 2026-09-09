-- 20260909022544_add_welcome_onboarding_preferences
-- +migrate Up
-- +migrate Dialect postgres
ALTER TABLE user_ui_preferences
    ADD COLUMN IF NOT EXISTS welcome_onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE user_ui_preferences
    ADD COLUMN IF NOT EXISTS welcome_identity VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE user_ui_preferences
    ADD COLUMN IF NOT EXISTS welcome_tasks JSONB NOT NULL DEFAULT '[]'::jsonb;
UPDATE user_ui_preferences SET welcome_onboarding_completed = TRUE;

-- +migrate Dialect sqlite
ALTER TABLE user_ui_preferences ADD COLUMN welcome_onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE user_ui_preferences ADD COLUMN welcome_identity VARCHAR(64) NOT NULL DEFAULT '';
ALTER TABLE user_ui_preferences ADD COLUMN welcome_tasks JSON NOT NULL DEFAULT '[]';
UPDATE user_ui_preferences SET welcome_onboarding_completed = TRUE;
