CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT NOT NULL,
    guild_id BIGINT NOT NULL,
    confirmed_by BIGINT NOT NULL,
    submitted_by BIGINT NOT NULL,
    context TEXT NOT NULL,
    author_id BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    logs JSON NOT NULL,
    expire BIGINT NOT NULL,
    PRIMARY KEY (ticket_id)
);
