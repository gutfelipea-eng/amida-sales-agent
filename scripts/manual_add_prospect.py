"""Manually add a prospect to the database."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import select

from amida_agent.database import get_session, init_db
from amida_agent.models import PEFirm, Prospect, ProspectStatus, RoleType


def main():
    parser = argparse.ArgumentParser(description="Add a prospect manually")
    parser.add_argument("--first-name", required=True)
    parser.add_argument("--last-name", required=True)
    parser.add_argument("--title", default="")
    parser.add_argument("--firm", default="", help="PE firm name (must exist in DB)")
    parser.add_argument("--linkedin", default="")
    parser.add_argument("--email", default="")
    parser.add_argument("--role-type", default="other", choices=[r.value for r in RoleType])
    parser.add_argument("--headline", default="")
    parser.add_argument("--location", default="")
    parser.add_argument("--source", default="manual")
    args = parser.parse_args()

    init_db()

    with get_session() as session:
        firm_id = None
        if args.firm:
            firm = session.exec(select(PEFirm).where(PEFirm.name == args.firm)).first()
            if firm:
                firm_id = firm.id
            else:
                print(f"Warning: PE firm '{args.firm}' not found in DB. Adding without firm link.")

        prospect = Prospect(
            first_name=args.first_name,
            last_name=args.last_name,
            full_name=f"{args.first_name} {args.last_name}",
            title=args.title,
            role_type=RoleType(args.role_type),
            linkedin_url=args.linkedin,
            email=args.email or None,
            headline=args.headline,
            location=args.location,
            source=args.source,
            status=ProspectStatus.new,
            pe_firm_id=firm_id,
        )
        session.add(prospect)
        session.commit()
        session.refresh(prospect)
        print(f"Added prospect: {prospect.full_name} (ID: {prospect.id})")


if __name__ == "__main__":
    main()
