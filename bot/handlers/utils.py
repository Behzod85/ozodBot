from models import User


def is_director(session, tg_id: int) -> bool:
    d = session.query(User).filter(User.telegram_id == tg_id, User.role == "director", User.approved == True).first()
    return bool(d)
