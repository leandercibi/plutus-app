from plutus.db.session import Base, engine
from plutus.db import models  # noqa: F401 — import all models so they register with Base


def init():
    Base.metadata.create_all(bind=engine)
    print("All tables created.")


if __name__ == "__main__":
    init()
