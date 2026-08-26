CREATE TABLE IF NOT EXISTS users (
  id SERIAL PRIMARY KEY,
  email VARCHAR(320) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  company_name VARCHAR(255) NOT NULL,
  is_verified BOOLEAN NOT NULL DEFAULT FALSE,
  is_admin BOOLEAN NOT NULL DEFAULT FALSE,
  created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS partner_profiles (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  role VARCHAR(20) NOT NULL DEFAULT 'lead',
  partner_name TEXT NOT NULL DEFAULT '',
  partner_short VARCHAR(100) NOT NULL DEFAULT '',
  address TEXT NOT NULL DEFAULT '',
  partner_ceo VARCHAR(255) NOT NULL DEFAULT '',
  partner_md1 VARCHAR(255) NOT NULL DEFAULT '',
  partner_md2 VARCHAR(255) NOT NULL DEFAULT '',
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS drafts (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name VARCHAR(255) NOT NULL,
  field_data JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_years (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  fiscal_year VARCHAR(20) NOT NULL,
  turnover_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_financial_year_user_year UNIQUE(user_id, fiscal_year)
);

CREATE TABLE IF NOT EXISTS financial_jv_entries (
  id SERIAL PRIMARY KEY,
  financial_year_id INTEGER NOT NULL REFERENCES financial_years(id) ON DELETE CASCADE,
  jv_name VARCHAR(255) NOT NULL DEFAULT '',
  jv_address TEXT NOT NULL DEFAULT '',
  vat_number VARCHAR(100) NOT NULL DEFAULT '',
  attributed_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
  share_percentage NUMERIC(7,2) NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS experiences (
  id SERIAL PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  start_month_year VARCHAR(30) NOT NULL DEFAULT '',
  end_month_year VARCHAR(30) NOT NULL DEFAULT '',
  contract_id VARCHAR(255) NOT NULL DEFAULT '',
  contract_name TEXT NOT NULL DEFAULT '',
  employer_name VARCHAR(255) NOT NULL DEFAULT '',
  employer_address TEXT NOT NULL DEFAULT '',
  employer_phone VARCHAR(100) NOT NULL DEFAULT '',
  employer_email VARCHAR(320) NOT NULL DEFAULT '',
  work_description TEXT NOT NULL DEFAULT '',
  role VARCHAR(40) NOT NULL DEFAULT 'Contractor',
  award_date VARCHAR(30) NOT NULL DEFAULT '',
  completion_date VARCHAR(30) NOT NULL DEFAULT '',
  total_contract_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
  participation_percentage NUMERIC(7,2) NOT NULL DEFAULT 100,
  participation_amount NUMERIC(18,2) NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS nrb_indices (
  id SERIAL PRIMARY KEY,
  fiscal_year VARCHAR(20) NOT NULL UNIQUE,
  index_value NUMERIC(12,4) NOT NULL,
  updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS auth_tokens (
  token VARCHAR(128) PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  kind VARCHAR(30) NOT NULL,
  expires_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_partner_profiles_user ON partner_profiles(user_id);
CREATE INDEX IF NOT EXISTS idx_drafts_user ON drafts(user_id);
CREATE INDEX IF NOT EXISTS idx_financial_years_user ON financial_years(user_id);
CREATE INDEX IF NOT EXISTS idx_experiences_user ON experiences(user_id);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_user_kind ON auth_tokens(user_id, kind);
