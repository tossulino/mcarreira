-- Esquema do banco D1 (Cloudflare). Rode no console do D1 (Dashboard → D1 → sua base → Console).
CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY, email TEXT UNIQUE, name TEXT,
  pw_salt TEXT, pw_hash TEXT, linkedin_sub TEXT, picture TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS sessions(
  token TEXT PRIMARY KEY, user_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS profiles(
  user_id INTEGER PRIMARY KEY, objetivo TEXT, setor TEXT, senioridade TEXT,
  voz TEXT, headline TEXT, sobre TEXT,
  respostas INTEGER DEFAULT 0, conversas INTEGER DEFAULT 0, entrevistas INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS ssi_snapshots(
  id INTEGER PRIMARY KEY, user_id INTEGER, score INTEGER,
  marca INTEGER, pessoas INTEGER, insights INTEGER, relacionamentos INTEGER,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS suggestions(
  id INTEGER PRIMARY KEY, user_id INTEGER, secao TEXT, sugestao TEXT, porque TEXT,
  status TEXT DEFAULT 'sugerido', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS threads(
  id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, role TEXT, color TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY, thread_id INTEGER, author TEXT, body TEXT,
  created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS jobfit(
  id INTEGER PRIMARY KEY, user_id INTEGER, vaga TEXT, aderencia INTEGER,
  atende TEXT, gaps TEXT, plano TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS leads(
  id INTEGER PRIMARY KEY, email TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
