-- =====================================================
-- highlight-ai database schema
-- Database: SQLite
-- Version: v1.0
-- Date: 2026-05-20
-- =====================================================

-- Enable foreign key support (SQLite requires this)
PRAGMA foreign_keys = ON;


-- =====================================================
-- Table 1: tasks
-- Stores every video the user has uploaded
-- =====================================================
CREATE TABLE tasks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,

    -- File info
    file_path       TEXT NOT NULL,
    file_name       TEXT NOT NULL,
    file_size       INTEGER,

    -- Video metadata
    duration_sec    REAL,
    width           INTEGER,
    height          INTEGER,
    fps             REAL,

    -- Game type (affects which AI model to load)
    game_type       TEXT,

    -- Processing status
    status          TEXT NOT NULL DEFAULT 'pending',
    progress        INTEGER DEFAULT 0,
    error_message   TEXT,

    -- Timestamps
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at    TIMESTAMP
);

-- Indexes for fast lookup
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created_at ON tasks(created_at DESC);


-- =====================================================
-- Table 2: highlights
-- AI-detected highlight segments for each task
-- =====================================================
CREATE TABLE highlights (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL,

    -- Time range in source video
    start_sec       REAL NOT NULL,
    end_sec         REAL NOT NULL,

    -- AI scores (0-100)
    score           INTEGER,
    score_ocr       INTEGER,
    score_audio     INTEGER,
    score_visual    INTEGER,

    -- AI-generated metadata
    label           TEXT,
    reason          TEXT,
    thumbnail_path  TEXT,

    -- User interaction state
    is_selected     BOOLEAN DEFAULT 1,
    user_modified   BOOLEAN DEFAULT 0,

    sort_order      INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX idx_highlights_task_id ON highlights(task_id);
CREATE INDEX idx_highlights_score ON highlights(score DESC);


-- =====================================================
-- Table 3: clips
-- Exported short videos (one task can have multiple clips)
-- =====================================================
CREATE TABLE clips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id         INTEGER NOT NULL,

    -- Output file
    output_path     TEXT NOT NULL,
    file_size       INTEGER,
    duration_sec    REAL,

    -- Output settings
    aspect_ratio    TEXT,
    resolution      TEXT,

    -- BGM settings
    bgm_id          INTEGER,
    bgm_volume      REAL DEFAULT 0.4,
    voice_volume    REAL DEFAULT 0.8,

    -- Subtitle settings
    has_subtitle    BOOLEAN DEFAULT 1,

    -- Which highlights were used (JSON array string)
    highlight_ids   TEXT,

    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
    FOREIGN KEY (bgm_id) REFERENCES bgm(id) ON DELETE SET NULL
);

CREATE INDEX idx_clips_task_id ON clips(task_id);


-- =====================================================
-- Table 4: bgm
-- Pre-loaded BGM library (static data)
-- =====================================================
CREATE TABLE bgm (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    file_path       TEXT NOT NULL,
    style           TEXT,
    duration_sec    REAL,
    license         TEXT,
    sort_order      INTEGER
);

CREATE INDEX idx_bgm_style ON bgm(style);


-- =====================================================
-- Table 5: subtitles (optional, may be dropped in Week 8)
-- Per-line subtitles for each clip
-- =====================================================
CREATE TABLE subtitles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id         INTEGER NOT NULL,

    start_sec       REAL NOT NULL,
    end_sec         REAL NOT NULL,
    text            TEXT NOT NULL,
    language        TEXT DEFAULT 'zh',

    FOREIGN KEY (clip_id) REFERENCES clips(id) ON DELETE CASCADE
);

CREATE INDEX idx_subtitles_clip_id ON subtitles(clip_id);


-- =====================================================
-- Table 6: settings
-- Key-value store for user preferences
-- =====================================================
CREATE TABLE settings (
    key             TEXT PRIMARY KEY,
    value           TEXT,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- =====================================================
-- Seed data: default settings
-- =====================================================
INSERT INTO settings (key, value) VALUES
    ('default_aspect_ratio', '16:9'),
    ('default_resolution',   '1080p'),
    ('default_bgm_style',    'epic'),
    ('primary_game',         'naraka'),
    ('auto_subtitle',        'true'),
    ('use_gpu',              'true'),
    ('output_dir',           '~/Videos/HighlightAI/');