from pathlib import Path
from datetime import datetime

from peewee import SqliteDatabase, Model, CharField, TextField, ForeignKeyField, DateTimeField, BooleanField
import ollama
from orun.utils import Colors, colored, print_warning, print_success, print_error, print_info, ensure_ollama_running

DB_DIR = Path.home() / ".orun"
DB_PATH = DB_DIR / "main.db"

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


class AIModel(BaseModel):
    full_name = CharField(unique=True)
    shortcut = CharField(unique=True)
    is_active = BooleanField(default=False)
    created_at = DateTimeField(default=datetime.now)


def initialize():
    """Initialize database connection and tables."""
    db.connect(reuse_if_open=True)
    db.create_tables([Conversation, Message, AIModel])
    
    # Migration: Ensure is_active column exists
    try:
        db.execute_sql('SELECT is_active FROM aimodel LIMIT 1')
    except Exception:
        db.execute_sql('ALTER TABLE aimodel ADD COLUMN is_active BOOLEAN DEFAULT 0')


def refresh_ollama_models():
    """Syncs models from Ollama to the database.
    
    - Adds new models with shortcut = full_name.
    - Preserves existing models and their shortcuts.
    """
    ensure_ollama_running()
    try:
        ollama_response = ollama.list()
        if ollama_response and ollama_response.get('models'):
            current_full_names = {m.full_name for m in AIModel.select()}
            current_shortcuts = {m.shortcut for m in AIModel.select()}
            new_models_data = []
            
            for m in ollama_response['models']:
                full_name = m['name']
                if full_name not in current_full_names:
                    # Check if shortcut is taken by another model
                    if full_name in current_shortcuts:
                        print_warning(f"Model '{full_name}' found in Ollama but its name conflicts with an existing shortcut. Skipping auto-add.")
                        continue
                    new_models_data.append({"full_name": full_name, "shortcut": full_name})
            
            if new_models_data:
                with db.atomic():
                    AIModel.insert_many(new_models_data).execute()
                print_success(f"Synced {len(new_models_data)} new models from Ollama.")
            else:
                print(colored("No new models to sync.", Colors.GREY))
                
    except Exception as e:
        print_error(f"Could not refresh Ollama models: {e}")


def update_model_shortcut(identifier: str, new_shortcut: str) -> bool:
    """Updates the shortcut for a model identified by name or current shortcut."""
    # Try finding by full_name first
    model = AIModel.get_or_none(AIModel.full_name == identifier)
    if not model:
        # Try finding by shortcut
        model = AIModel.get_or_none(AIModel.shortcut == identifier)
    
    if not model:
        return False
        
    try:
        model.shortcut = new_shortcut
        model.save()
        return True
    except Exception:
        # Likely unique constraint violation
        return False


def get_models() -> dict[str, str]:
    """Get all models as a dictionary of shortcut -> full_name."""
    return {m.shortcut: m.full_name for m in AIModel.select()}


def set_active_model(model_name: str):
    """Set the active model."""
    # Reset all
    AIModel.update(is_active=False).execute()
    # Set new active. Try to match full_name first, then shortcut.
    query = AIModel.update(is_active=True).where(AIModel.full_name == model_name)
    if query.execute() == 0:
        AIModel.update(is_active=True).where(AIModel.shortcut == model_name).execute()


def get_active_model() -> str | None:
    """Get the currently active model name."""
    model = AIModel.select().where(AIModel.is_active == True).first()
    return model.full_name if model else None


def create_conversation(model: str) -> int:
    """Create a new conversation and return its ID."""
    conversation = Conversation.create(model=model)
    return conversation.id


def add_message(conversation_id: int, role: str, content: str, images: list[str] | None = None):
    """Add a message to a conversation."""
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
    messages = []
    for msg in Message.select().where(Message.conversation_id == conversation_id).order_by(Message.id):
        m = {"role": msg.role, "content": msg.content}
        if msg.images:
            m["images"] = msg.images.split(",")
        messages.append(m)
    return messages


def get_recent_conversations(limit: int = 10) -> list[dict]:
    """Get recent conversations."""
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
    conv = Conversation.select().order_by(Conversation.updated_at.desc()).first()
    return conv.id if conv else None


def get_conversation(conversation_id: int) -> dict | None:
    """Get a conversation by ID."""
    conv = Conversation.get_or_none(Conversation.id == conversation_id)
    if not conv:
        return None
    return {
        "id": conv.id,
        "model": conv.model,
        "created_at": conv.created_at.isoformat(),
        "updated_at": conv.updated_at.isoformat()
    }