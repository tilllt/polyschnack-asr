"""ledger.py — Buchungs-Journal der virtuellen Credits (Change 086).

Append-only Journal (CreditLedger) + Saldo-Führung auf dem User.
Reserve-System: beim Job-Start wird ein Vorschuss reserviert
(Recording.reserved_cents), bei Abschluss wird nur das Delta gebucht —
der Saldo kann nie ins Negative (clamp), das Journal bleibt trotzdem
exakt (echte Kosten werden immer in voller Höhe verbucht).
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlmodel import Session, select

from .models import CreditLedger, User

log = logging.getLogger(__name__)

#: Startguthaben für neue User (test-Tier, virtuell) — 10,00 €.
SIGNUP_BONUS_CENTS = 1000


def topup(
    session: Session,
    user_id: int,
    amount_cents: int,
    reason: str = "topup",
    created_by: Optional[int] = None,
) -> Optional[User]:
    """Guthaben erhöhen (Admin-TopUp, signup_bonus, refund). Append-only."""
    if amount_cents <= 0:
        return None
    user = session.get(User, user_id)
    if user is None:
        return None
    user.credits_cents += amount_cents
    session.add(user)
    session.add(CreditLedger(
        user_id=user_id,
        delta_cents=amount_cents,
        reason=reason,
        created_by=created_by,
    ))
    session.commit()
    session.refresh(user)
    return user


def book_job_cost(session: Session, user_id: int, rec_id: int, cost_cents: int) -> None:
    """Ist-Kosten nach Job-Abschluss buchen (Delta zur Reserve).

    Journal immer exakt (volle −cost_cents); Saldo wird geclampt auf 0 —
    ein Negativ-Konto ist mit dem Reserve-System ein Fehlerfall, kein
    Zustand. Owner-None (public recordings) wird übersprungen.
    """
    if cost_cents <= 0 or user_id is None:
        return
    user = session.get(User, user_id)
    if user is None:
        return
    delta = -cost_cents
    new_balance = user.credits_cents + delta
    if new_balance < 0:
        log.warning(
            "credits: user_id=%s wäre unter 0 (Saldo %d, cost %d) — clamp; "
            "Reserve-System prüfen", user_id, user.credits_cents, cost_cents,
        )
        new_balance = 0
    user.credits_cents = new_balance
    session.add(user)
    session.add(CreditLedger(
        user_id=user_id,
        delta_cents=delta,
        reason="job_cost",
        ref_id=rec_id,
    ))
    session.commit()


def ledger_for_user(session: Session, user_id: int, limit: int = 20) -> List[CreditLedger]:
    """Letzte Buchungen eines Users (neueste zuerst)."""
    return session.exec(
        select(CreditLedger)
        .where(CreditLedger.user_id == user_id)
        .order_by(CreditLedger.id.desc())
        .limit(limit)
    ).all()


def ledger_all(
    session: Session,
    limit: int = 100,
    user_id: Optional[int] = None,
) -> List[CreditLedger]:
    """Journal für den Admin (neueste zuerst, optional gefiltert)."""
    stmt = select(CreditLedger).order_by(CreditLedger.id.desc())
    if user_id is not None:
        stmt = stmt.where(CreditLedger.user_id == user_id)
    return session.exec(stmt.limit(limit)).all()


def user_spent_cents(session: Session, user_id: int) -> int:
    """Σ aller job_cost-Buchungen eines Users (Verbrauch, für Admin-Liste)."""
    rows = session.exec(
        select(CreditLedger.delta_cents).where(
            CreditLedger.user_id == user_id,
            CreditLedger.delta_cents < 0,
        )
    ).all()
    return -sum(r for r in rows if r is not None)
