from pathlib import Path
from datetime import datetime

from peewee import SqliteDatabase, Model, CharField, TextField, ForeignKeyField, DateTimeField

DB_DIR = Path.home() / ".orun"
DB_PATH = DB_DIR / "history.db"

DB_DIR.mkdir(parents=True, exist_ok=True)
db = SqliteDatabase(DB_PATH)


class BaseModel(Model):
    class Meta:
        database = db


class Conversation(BaseModel):
    model = CharField()
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)


class Message(BaseModel):
    conversation = ForeignKeyField(Conversation, backref='messages', on_delete='CASCADE')
    role = CharField()
    content = TextField()
    images = TextField(null=True)
    created_at = DateTimeField(default=datetime.now)


def init_db():
    """Initialize database tables."""
    db.connect(reuse_if_open=True)
    db.create_tables([Conversation, Message])


def create_conversation(model: str) -> int:
    """Create a new conversation and return its ID."""
    init_db()
    conversation = Conversation.create(model=model)
    return conversation.id


def add_message(conversation_id: int, role: str, content: str, images: list[str] | None = None):
    """Add a message to a conversation."""
    init_db()
    images_str = ",".join(images) if images else None
    Message.create(
        conversation_id=conversation_id,
        role=role,
        content=content,
        images=images_str
    )
    Conversation.update(updated_at=datetime.now()).where(Conversation.id == conversation_id).execute()


def get_conversation_messages(conversation_id: int) -> list[dict]:
    """Get all messages for a conversation."""
    init_db()
    messages = []
    for msg in Message.select().where(Message.conversation_id == conversation_id).order_by(Message.id):
        m = {"role": msg.role, "content": msg.content}
        if msg.images:
            m["images"] = msg.images.split(",")
        messages.append(m)
    return messages


def get_recent_conversations(limit: int = 10) -> list[dict]:
    """Get recent conversations."""
    init_db()
    conversations = []
    for conv in Conversation.select().order_by(Conversation.updated_at.desc()).limit(limit):
        conversations.append({
            "id": conv.id,
            "model": conv.model,
            "created_at": conv.created_at.isoformat(),
            "updated_at": conv.updated_at.isoformat()
        })
    return conversations


def get_last_conversation_id() -> int | None:
    """Get the ID of the most recent conversation."""
    init_db()
    conv = Conversation.select().order_by(Conversation.updated_at.desc()).first()
    return conv.id if conv else None


def get_conversation(conversation_id: int) -> dict | None:
    """Get a conversation by ID."""
    init_db()
    conv = Conversation.get_or_none(Conversation.id == conversation_id)
    if not conv:
        return None
    return {
        "id": conv.id,
        "model": conv.model,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat()
    }
