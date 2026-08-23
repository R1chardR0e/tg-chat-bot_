-- Пользователи
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    first_name TEXT,
    last_name TEXT,
    username TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Чаты
CREATE TABLE IF NOT EXISTS chats (
    chat_id TEXT PRIMARY KEY,
    type TEXT NOT NULL, -- private, group, supergroup, channel
    title TEXT,
    username TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Сообщения
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER NOT NULL, -- telegram_message_id
    chat_id TEXT NOT NULL,
    user_id TEXT,
    date DATETIME NOT NULL,
    edit_date DATETIME,
    forward_from_user_id TEXT,
    forward_from_chat_id TEXT,
    forward_from_message_id INTEGER,
    forward_signature TEXT,
    forward_sender_name TEXT,
    forward_date DATETIME,
    reply_to_message_id INTEGER,
    reply_to_user_id TEXT,
    media_type TEXT, -- text, photo, video, audio, voice, document, sticker, animation, poll, location, contact, venue, dice, game, invoice, story
    content TEXT, -- текст или описание медиа
    file_id TEXT,
    file_unique_id TEXT,
    file_size INTEGER,
    mime_type TEXT,
    duration INTEGER, -- для аудио/видео
    width INTEGER, -- фото/видео
    height INTEGER, -- фото/видео
    performer TEXT, -- аудио
    title TEXT, -- аудио/видео
    sticker_emoji TEXT,
    sticker_set_name TEXT,
    is_animated_sticker BOOLEAN,
    is_video_sticker BOOLEAN,
    poll_question TEXT,
    poll_options TEXT, -- JSON
    poll_total_voters INTEGER,
    poll_is_closed BOOLEAN,
    poll_is_anonymous BOOLEAN,
    poll_type TEXT,
    latitude REAL,
    longitude REAL,
    contact_phone_number TEXT,
    contact_first_name TEXT,
    contact_last_name TEXT,
    contact_vcard TEXT,
    venue_title TEXT,
    venue_address TEXT,
    venue_latitude REAL,
    venue_longitude REAL,
    dice_value INTEGER,
    game_title TEXT,
    game_description TEXT,
    invoice_title TEXT,
    invoice_description TEXT,
    invoice_total_amount INTEGER,
    invoice_currency TEXT,
    has_protected_content BOOLEAN,
    has_embedding BOOLEAN DEFAULT FALSE,
    FOREIGN KEY(chat_id) REFERENCES chats(chat_id),
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    FOREIGN KEY(forward_from_user_id) REFERENCES users(user_id),
    FOREIGN KEY(forward_from_chat_id) REFERENCES chats(chat_id),
    FOREIGN KEY(reply_to_user_id) REFERENCES users(user_id),
    UNIQUE(chat_id, message_id)
);

-- Indexes for performance
CREATE INDEX idx_messages_date ON messages(date);
CREATE INDEX idx_messages_chat_id ON messages(chat_id);
CREATE INDEX idx_messages_user_id ON messages(user_id);

-- Реакции
CREATE TABLE IF NOT EXISTS reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id INTEGER,
    chat_id TEXT,
    user_id TEXT,
    reaction TEXT NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(message_id, chat_id) REFERENCES messages(message_id, chat_id),
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    UNIQUE(message_id, chat_id, user_id, reaction)
);

-- Участники чатов
CREATE TABLE IF NOT EXISTS chat_members (
    chat_id TEXT,
    user_id TEXT,
    status TEXT, -- creator, administrator, member, restricted, left, kicked
    is_anonymous BOOLEAN,
    custom_title TEXT,
    until_date DATETIME,
    joined_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(chat_id) REFERENCES chats(chat_id),
    FOREIGN KEY(user_id) REFERENCES users(user_id),
    PRIMARY KEY(chat_id, user_id)
);

-- Хэши сообщений (для дедупликации)
CREATE TABLE IF NOT EXISTS message_hashes (
    hash TEXT PRIMARY KEY
);

-- Таблица для сопоставления векторов FAISS и записей базы данных
CREATE TABLE IF NOT EXISTS faiss_index_mappings (
    mapping_id INTEGER PRIMARY KEY AUTOINCREMENT,
    vector_id INTEGER NOT NULL, -- ID вектора в FAISS индексе
    database_id INTEGER NOT NULL, -- ID сообщения в таблице messages
    chat_id TEXT NOT NULL, -- ID чата для быстрой фильтрации
    sync_status TEXT DEFAULT 'pending', -- Статус синхронизации: pending, synced, failed
    last_sync_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(database_id) REFERENCES messages(id),
    FOREIGN KEY(chat_id) REFERENCES chats(chat_id),
    UNIQUE(vector_id, database_id)
);

-- Индексы для производительности
CREATE INDEX idx_faiss_mappings_database_id ON faiss_index_mappings(database_id);
CREATE INDEX idx_faiss_mappings_chat_id ON faiss_index_mappings(chat_id);
CREATE INDEX idx_faiss_mappings_sync_status ON faiss_index_mappings(sync_status);
CREATE INDEX idx_faiss_mappings_vector_id ON faiss_index_mappings(vector_id);