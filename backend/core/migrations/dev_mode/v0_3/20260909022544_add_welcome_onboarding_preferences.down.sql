-- 20260909022544_add_welcome_onboarding_preferences
-- +migrate Down
-- +migrate Dialect postgres
ALTER TABLE user_ui_preferences
    DROP COLUMN IF EXISTS welcome_tasks,
    DROP COLUMN IF EXISTS welcome_identity,
    DROP COLUMN IF EXISTS welcome_onboarding_completed;

-- +migrate Dialect sqlite
ALTER TABLE user_ui_preferences DROP COLUMN welcome_tasks;
ALTER TABLE user_ui_preferences DROP COLUMN welcome_identity;
ALTER TABLE user_ui_preferences DROP COLUMN welcome_onboarding_completed;
