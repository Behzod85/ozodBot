from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    String,
    Boolean,
    ForeignKey,
    DateTime,
    Text,
    text,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import datetime

DB_URL = "sqlite:///ozodbot.db"
engine = create_engine(DB_URL, connect_args={"check_same_thread": False}, echo=False)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    name = Column(String)
    role = Column(String, default="pending")  # pending, client, worker, director
    approved = Column(Boolean, default=False)

    orders = relationship("Order", back_populates="client")
    assigned_steps = relationship("OrderStep", back_populates="assigned_to")


class Template(Base):
    __tablename__ = "templates"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    steps = relationship(
        "TemplateStep",
        order_by="TemplateStep.position",
        back_populates="template",
        cascade="all, delete-orphan",
    )


class TemplateStep(Base):
    __tablename__ = "template_steps"
    id = Column(Integer, primary_key=True)
    template_id = Column(Integer, ForeignKey("templates.id"))
    position = Column(Integer)
    # Removed: role, instruction_text, notification_text -- now steps reference reusable `Process` rows.
    process_id = Column(Integer, ForeignKey("processes.id"), nullable=True)
    template = relationship("Template", back_populates="steps")
    process = relationship("Process", back_populates="template_steps")


class Process(Base):
    __tablename__ = "processes"
    id = Column(Integer, primary_key=True)
    instruction_text = Column(Text)
    notification_text = Column(Text)
    template_steps = relationship("TemplateStep", back_populates="process")


# NOTE: TemplateStep holds either inline texts or a process reference in `process_id`.


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey("users.id"))
    template_id = Column(Integer, ForeignKey("templates.id"))
    name = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String, default="created")  # created, running, completed
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    client = relationship("User", back_populates="orders")
    template = relationship("Template")
    steps = relationship("OrderStep", order_by="OrderStep.position", back_populates="order")


class OrderStep(Base):
    __tablename__ = "order_steps"
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"))
    template_step_id = Column(Integer, ForeignKey("template_steps.id"))
    position = Column(Integer)
    role = Column(String, default="worker")
    instruction_text = Column(Text)
    notification_text = Column(Text)
    status = Column(String, default="pending")  # pending, assigned, in_progress, done
    assigned_to_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    order = relationship("Order", back_populates="steps")
    assigned_to = relationship("User", back_populates="assigned_steps")


def init_db():
    Base.metadata.create_all(bind=engine)
    # Add new columns to existing SQLite table if they are missing (safe ALTER TABLE add column)
    try:
        with engine.connect() as conn:
            res = conn.execute(text("PRAGMA table_info(orders)"))
            cols = [row[1] for row in res.fetchall()]
            if "name" not in cols:
                conn.execute(text("ALTER TABLE orders ADD COLUMN name VARCHAR"))
            if "description" not in cols:
                conn.execute(text("ALTER TABLE orders ADD COLUMN description TEXT"))
            # ensure template_steps has process_id column for new Process model
            res2 = conn.execute(text("PRAGMA table_info(template_steps)"))
            cols2 = [row[1] for row in res2.fetchall()]
            if "process_id" not in cols2:
                try:
                    conn.execute(text("ALTER TABLE template_steps ADD COLUMN process_id INTEGER"))
                except Exception:
                    # best-effort: ignore if ALTER fails
                    pass
            # Non-destructive migration: convert any inline step texts into Process rows
            # and set template_steps.process_id accordingly, then rebuild the table
            # without the legacy columns (role, instruction_text, notification_text).
            legacy_cols = {"role", "instruction_text", "notification_text"}
            existing_legacy = legacy_cols.intersection(set(cols2))
            if existing_legacy:
                try:
                    # Ensure we have a process_id column to write into
                    if "process_id" not in cols2:
                        try:
                            conn.execute(text("ALTER TABLE template_steps ADD COLUMN process_id INTEGER"))
                        except Exception:
                            pass
                        # refresh columns
                        res2 = conn.execute(text("PRAGMA table_info(template_steps)"))
                        cols2 = [row[1] for row in res2.fetchall()]

                    # Find template_steps rows that have inline texts and no process_id yet
                    try:
                        rows = conn.execute(text(
                            "SELECT id, instruction_text, notification_text FROM template_steps "
                            "WHERE (((instruction_text IS NOT NULL AND TRIM(instruction_text) <> '') OR (notification_text IS NOT NULL AND TRIM(notification_text) <> '')) AND (process_id IS NULL))"
                        )).fetchall()
                    except Exception:
                        rows = []

                    for r in rows:
                        try:
                            ts_id = r[0]
                            instr = r[1]
                            notif = r[2]
                            # insert a new Process row with these texts
                            conn.execute(text("INSERT INTO processes (instruction_text, notification_text) VALUES (:instr, :notif)"), {"instr": instr, "notif": notif})
                            new_pid = conn.execute(text("SELECT last_insert_rowid()")).fetchone()[0]
                            # link the template step to the new process
                            conn.execute(text("UPDATE template_steps SET process_id = :pid WHERE id = :id"), {"pid": new_pid, "id": ts_id})
                        except Exception:
                            # best-effort: skip problematic rows
                            pass

                    # Now rebuild the template_steps table without legacy columns
                    conn.execute(text("PRAGMA foreign_keys=off"))
                    conn.execute(text(
                        """
                        CREATE TABLE IF NOT EXISTS template_steps_new (
                            id INTEGER PRIMARY KEY,
                            template_id INTEGER,
                            position INTEGER,
                            process_id INTEGER,
                            FOREIGN KEY(template_id) REFERENCES templates(id),
                            FOREIGN KEY(process_id) REFERENCES processes(id)
                        )
                        """
                    ))
                    # Copy id/template_id/position/process_id (process_id may be NULL)
                    conn.execute(text(
                        "INSERT OR IGNORE INTO template_steps_new (id, template_id, position, process_id) SELECT id, template_id, position, process_id FROM template_steps"
                    ))
                    conn.execute(text("DROP TABLE template_steps"))
                    conn.execute(text("ALTER TABLE template_steps_new RENAME TO template_steps"))
                except Exception:
                    # migration best-effort; ignore failures here
                    pass
                finally:
                    try:
                        conn.execute(text("PRAGMA foreign_keys=on"))
                    except Exception:
                        pass
    except Exception:
        # Don't fail init if migration isn't possible in this environment
        pass
