"""Seed the database with the target PE firm list."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import func, select

from amida_agent.database import get_session, init_db
from amida_agent.models import PEFirm

PE_FIRMS = [
    {
        "name": "EQT",
        "website": "https://eqtgroup.com",
        "linkedin_url": "https://www.linkedin.com/company/eqt-group/",
        "country": "Sweden",
        "hq_city": "Stockholm",
        "aum_billion_eur": 232,
        "sectors": "technology,healthcare,services",
    },
    {
        "name": "Fidelio Capital",
        "website": "https://fideliocapital.com",
        "linkedin_url": "https://www.linkedin.com/company/fidelio-capital/",
        "country": "Sweden",
        "hq_city": "Stockholm",
        "sectors": "industrials,technology,services",
    },
    {
        "name": "IK Partners",
        "website": "https://ikpartners.com",
        "linkedin_url": "https://www.linkedin.com/company/ik-partners/",
        "country": "Sweden",
        "hq_city": "Stockholm",
        "aum_billion_eur": 14,
        "sectors": "healthcare,industrials,consumer",
    },
    {
        "name": "Nordic Capital",
        "website": "https://nordiccapital.com",
        "linkedin_url": "https://www.linkedin.com/company/nordic-capital/",
        "country": "Sweden",
        "hq_city": "Stockholm",
        "aum_billion_eur": 22,
        "sectors": "healthcare,technology,financial_services",
    },
    {
        "name": "Altor",
        "website": "https://altor.com",
        "linkedin_url": "https://www.linkedin.com/company/altor-equity-partners/",
        "country": "Sweden",
        "hq_city": "Stockholm",
        "aum_billion_eur": 10,
        "sectors": "industrials,services,consumer",
    },
    {
        "name": "Summa Equity",
        "website": "https://summaequity.com",
        "linkedin_url": "https://www.linkedin.com/company/summa-equity/",
        "country": "Norway",
        "hq_city": "Oslo",
        "aum_billion_eur": 4,
        "sectors": "technology,education,resource_efficiency",
    },
    {
        "name": "Verdane",
        "website": "https://verdane.com",
        "linkedin_url": "https://www.linkedin.com/company/verdane/",
        "country": "Norway",
        "hq_city": "Oslo",
        "aum_billion_eur": 6,
        "sectors": "technology,sustainability",
    },
    {
        "name": "Hg Capital",
        "website": "https://hgcapital.com",
        "linkedin_url": "https://www.linkedin.com/company/hg-capital/",
        "country": "UK",
        "hq_city": "London",
        "aum_billion_eur": 65,
        "sectors": "software,technology,services",
    },
    {
        "name": "Cinven",
        "website": "https://cinven.com",
        "linkedin_url": "https://www.linkedin.com/company/cinven/",
        "country": "UK",
        "hq_city": "London",
        "aum_billion_eur": 40,
        "sectors": "healthcare,technology,financial_services",
    },
    {
        "name": "Triton",
        "website": "https://triton-partners.com",
        "linkedin_url": "https://www.linkedin.com/company/triton-partners/",
        "country": "Germany",
        "hq_city": "Frankfurt",
        "aum_billion_eur": 22,
        "sectors": "industrials,services,consumer",
    },
    {
        "name": "Advent International",
        "website": "https://adventinternational.com",
        "linkedin_url": "https://www.linkedin.com/company/advent-international/",
        "country": "US",
        "hq_city": "Boston",
        "aum_billion_eur": 90,
        "sectors": "technology,healthcare,financial_services",
    },
    {
        "name": "Permira",
        "website": "https://permira.com",
        "linkedin_url": "https://www.linkedin.com/company/permira/",
        "country": "UK",
        "hq_city": "London",
        "aum_billion_eur": 80,
        "sectors": "technology,consumer,healthcare",
    },
    {
        "name": "Bridgepoint",
        "website": "https://bridgepoint.eu",
        "linkedin_url": "https://www.linkedin.com/company/bridgepoint/",
        "country": "UK",
        "hq_city": "London",
        "aum_billion_eur": 40,
        "sectors": "healthcare,technology,services",
    },
    {
        "name": "FSN Capital",
        "website": "https://fsncapital.com",
        "linkedin_url": "https://www.linkedin.com/company/fsn-capital/",
        "country": "Norway",
        "hq_city": "Oslo",
        "aum_billion_eur": 5,
        "sectors": "services,industrials,technology",
    },
    {
        "name": "Accent Equity",
        "website": "https://accentequity.se",
        "linkedin_url": "https://www.linkedin.com/company/accent-equity-partners/",
        "country": "Sweden",
        "hq_city": "Stockholm",
        "aum_billion_eur": 2,
        "sectors": "industrials,technology,healthcare",
    },
    {
        "name": "Segulah",
        "website": "https://segulah.se",
        "linkedin_url": "https://www.linkedin.com/company/segulah/",
        "country": "Sweden",
        "hq_city": "Stockholm",
        "sectors": "industrials,services",
    },
    {
        "name": "Procuritas",
        "website": "https://procuritas.com",
        "linkedin_url": "https://www.linkedin.com/company/procuritas-partners/",
        "country": "Sweden",
        "hq_city": "Stockholm",
        "sectors": "industrials,services,healthcare",
    },
    {
        "name": "Norvestor",
        "website": "https://norvestor.com",
        "linkedin_url": "https://www.linkedin.com/company/norvestor/",
        "country": "Norway",
        "hq_city": "Oslo",
        "aum_billion_eur": 3,
        "sectors": "technology,services,industrials",
    },
    {
        "name": "Polaris",
        "website": "https://polarisequity.dk",
        "linkedin_url": "https://www.linkedin.com/company/polaris-management/",
        "country": "Denmark",
        "hq_city": "Copenhagen",
        "aum_billion_eur": 3,
        "sectors": "technology,services,industrials",
    },
    {
        "name": "Axcel",
        "website": "https://axcel.dk",
        "linkedin_url": "https://www.linkedin.com/company/axcel/",
        "country": "Denmark",
        "hq_city": "Copenhagen",
        "aum_billion_eur": 4,
        "sectors": "technology,industrials,food",
    },
    {
        "name": "Valedo",
        "website": "https://valedo.se",
        "linkedin_url": "https://www.linkedin.com/company/valedo-partners/",
        "country": "Sweden",
        "hq_city": "Stockholm",
        "sectors": "healthcare,services,industrials",
    },
    {
        "name": "Ratos",
        "website": "https://ratos.com",
        "linkedin_url": "https://www.linkedin.com/company/ratos/",
        "country": "Sweden",
        "hq_city": "Stockholm",
        "aum_billion_eur": 4,
        "sectors": "construction,industrials,technology",
    },
]


def seed() -> None:
    init_db()
    with get_session() as session:
        existing = {f.name for f in session.exec(select(PEFirm)).all()}
        added = 0
        for firm_data in PE_FIRMS:
            if firm_data["name"] not in existing:
                session.add(PEFirm(**firm_data))
                added += 1
        session.commit()
        total = session.exec(select(func.count(PEFirm.id))).one()
    print(f"Added {added} new PE firms. Total in DB: {total}")


if __name__ == "__main__":
    seed()
