"""Registers a community, interactively. Runs inside the ln2oc container:
scripts/register_community.sh (wrapper around `docker compose exec`)."""
import sys

from app.community import NAME_RULE, CommunityError, register
from app.db import SessionLocal, verify_schema


def main() -> int:
    verify_schema()
    print("Alta de comunidad")
    name = input(f"name (va en ?community=<name>; {NAME_RULE}): ").strip()
    contact = input("contact (texto libre: Telegram, mail, teléfono...): ").strip()
    print(f"\n  name:    {name}\n  contact: {contact}\n")
    if input("¿Crear la comunidad? [s/N]: ").strip().lower() != "s":
        print("Cancelado, no se creó nada.")
        return 1
    with SessionLocal() as db:
        try:
            community = register(db, name, contact)
        except CommunityError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    print(f"Comunidad creada: id {community.id}, name {community.name!r}. Sus usuarios: ?community={community.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
