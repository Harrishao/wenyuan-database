from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.models import SensitiveTerm


async def scan_sensitive_text(session: AsyncSession, text: str) -> list[dict]:
    terms = list(
        await session.scalars(
            select(SensitiveTerm)
            .where(SensitiveTerm.enabled.is_(True))
            .order_by(SensitiveTerm.term)
        )
    )
    hits: list[dict] = []
    lowered = text.lower()
    for item in terms:
        needle = item.term.lower()
        start = 0
        positions: list[int] = []
        while len(positions) < 20:
            index = lowered.find(needle, start)
            if index < 0:
                break
            positions.append(index)
            start = index + max(1, len(needle))
        if positions:
            hits.append(
                {
                    "term_id": str(item.id),
                    "term": item.term,
                    "category": item.category,
                    "count": lowered.count(needle),
                    "positions": positions,
                }
            )
    return hits
