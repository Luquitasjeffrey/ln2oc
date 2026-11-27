"""Shows what is owed to a community and, if the operator pays it now, records the
withdrawal. The payment itself is manual (ask the community for an invoice or a
Lightning Address). Runs inside the ln2oc container: scripts/withdraw_community_earnings.sh."""
import sys

from app.community import CommunityError, get_by_name, owed_sat, record_withdrawal
from app.db import SessionLocal, verify_schema


def main() -> int:
    verify_schema()
    name = input("name de la comunidad: ").strip()
    with SessionLocal() as db:
        community = get_by_name(db, name)
        if community is None:
            print(f"Error: no existe la comunidad {name!r}", file=sys.stderr)
            return 1
        owed = owed_sat(db, community.id)
        contact = community.contact
        print(f"\n  comunidad: {community.name} (id {community.id})\n  contact:   {community.contact}\n"
              f"  adeudado:  {owed} sats\n")
        if owed == 0:
            print("No hay nada para pagar.")
            return 0
        if input("¿Vas a [p]agar ahora o es [c]onsulta? [c]: ").strip().lower() != "p":
            print("Consulta: no se cambió nada.")
            return 0
        if input(f"Se registra un pago de {owed} sats y la deuda queda en 0. ¿Confirmás? [s/N]: ").strip().lower() != "s":
            print("Cancelado, no se cambió nada.")
            return 1
        try:
            record_withdrawal(db, community.id, owed)
        except CommunityError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    print(f"Registrado. Ahora pagale {owed} sats a mano a la comunidad ({contact}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
