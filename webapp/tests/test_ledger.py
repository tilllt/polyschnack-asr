"""Change 086: ledger.py — Buchungen, Saldo, Journal."""
import pytest

from app.db import init_db
from app.ledger import (
    SIGNUP_BONUS_CENTS,
    book_job_cost,
    ledger_all,
    ledger_for_user,
    topup,
    user_spent_cents,
)
from app.models import User
from sqlmodel import Session, select

from app.db import engine


@pytest.fixture(autouse=True)
def _cleanup():
    init_db()
    with Session(engine) as s:
        for u in s.exec(select(User)).all():
            s.delete(u)
        from app.models import CreditLedger
        for r in s.exec(select(CreditLedger)).all():
            s.delete(r)
        s.commit()
    yield
    with Session(engine) as s:
        for u in s.exec(select(User)).all():
            s.delete(u)
        from app.models import CreditLedger
        for r in s.exec(select(CreditLedger)).all():
            s.delete(r)
        s.commit()


def _mkuser() -> User:
    with Session(engine) as s:
        u = User(sub="sub-credits-test")
        s.add(u)
        s.commit()
        s.refresh(u)
        return u


def test_topup_erhoeht_saldo_und_bucht():
    u = _mkuser()
    with Session(engine) as s:
        topup(s, u.id, 500, reason="topup")
        u2 = s.get(User, u.id)
        assert u2.credits_cents == 500
        entries = ledger_for_user(s, u.id)
        assert len(entries) == 1
        assert entries[0].delta_cents == 500
        assert entries[0].reason == "topup"


def test_topup_ungueltig_kein_effekt():
    u = _mkuser()
    with Session(engine) as s:
        assert topup(s, u.id, 0) is None
        assert topup(s, u.id, -5) is None
        assert topup(s, 99999, 100) is None
        assert s.get(User, u.id).credits_cents == 0


def test_book_job_cost_zieht_ab():
    u = _mkuser()
    with Session(engine) as s:
        topup(s, u.id, 1000)
        book_job_cost(s, u.id, rec_id=42, cost_cents=250)
        u2 = s.get(User, u.id)
        assert u2.credits_cents == 750
        entries = ledger_for_user(s, u.id)
        assert entries[0].reason == "job_cost"
        assert entries[0].delta_cents == -250
        assert entries[0].ref_id == 42


def test_book_job_cost_clamp_bei_null():
    u = _mkuser()
    with Session(engine) as s:
        topup(s, u.id, 100)
        book_job_cost(s, u.id, rec_id=7, cost_cents=500)  # Saldo reicht nicht
        u2 = s.get(User, u.id)
        assert u2.credits_cents == 0
        # Journal bleibt exakt (echte Kosten)
        entries = ledger_for_user(s, u.id)
        assert entries[0].delta_cents == -500


def test_book_job_cost_ohne_saldo_kein_buch():
    u = _mkuser()
    with Session(engine) as s:
        book_job_cost(s, u.id, rec_id=1, cost_cents=0)   # nichts zu buchen
        book_job_cost(s, None, rec_id=1, cost_cents=50)  # public recording
        assert len(ledger_for_user(s, u.id)) == 0


def test_user_spent_cents():
    u = _mkuser()
    with Session(engine) as s:
        topup(s, u.id, 1000)
        book_job_cost(s, u.id, rec_id=1, cost_cents=300)
        book_job_cost(s, u.id, rec_id=2, cost_cents=200)
        assert user_spent_cents(s, u.id) == 500


def test_ledger_all_filter_und_limit():
    u = _mkuser()
    with Session(engine) as s:
        topup(s, u.id, 1000)
        book_job_cost(s, u.id, rec_id=1, cost_cents=100)
        book_job_cost(s, u.id, rec_id=2, cost_cents=100)
        all_rows = ledger_all(s, limit=10)
        assert len(all_rows) == 3
        filtered = ledger_all(s, limit=10, user_id=u.id)
        assert len(filtered) == 3
        assert ledger_all(s, limit=1)  # Limit greift


def test_signup_bonus_konstante():
    assert SIGNUP_BONUS_CENTS == 1000
