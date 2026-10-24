import pytest

from backend.algorithms import compute_balances, simplify_debts, split_equally


def test_split_equally_distributes_leftover_cents():
    assert split_equally(100, [1, 2, 3]) == {1: 34, 2: 33, 3: 33}
    assert sum(split_equally(1001, [1, 2, 3, 4, 5, 6, 7]).values()) == 1001


def test_split_equally_requires_members():
    with pytest.raises(ValueError):
        split_equally(100, [])


def test_compute_balances_with_expense_and_settlement():
    balances = compute_balances(
        [1, 2, 3],
        [(1, 300, {1: 100, 2: 100, 3: 100})],
        [(2, 1, 100)],
    )
    assert balances == {1: 100, 2: 0, 3: -100}
    assert sum(balances.values()) == 0


def test_simplify_debts_settles_everyone():
    balances = {1: 500, 2: -200, 3: -300, 4: 0}
    payments = simplify_debts(balances)
    assert payments == [(3, 1, 300), (2, 1, 200)]

    remaining = dict(balances)
    for debtor, creditor, amount in payments:
        remaining[debtor] += amount
        remaining[creditor] -= amount
    assert all(value == 0 for value in remaining.values())


def test_simplify_debts_uses_at_most_n_minus_one_payments():
    balances = {1: 700, 2: 300, 3: -250, 4: -250, 5: -500}
    assert len(simplify_debts(balances)) <= len(balances) - 1


def test_simplify_debts_all_settled():
    assert simplify_debts({1: 0, 2: 0}) == []
