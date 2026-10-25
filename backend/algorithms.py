def split_equally(amount_cents, member_ids):
    """
    Split an amount into equal integer shares, one per member.

    Leftover cents go one each to the first members, so the shares always
    add up to exactly amount_cents (e.g. 100 split 3 ways -> 34, 33, 33).
    """
    if not member_ids:
        raise ValueError("at least one member is required to split an expense")
    base, remainder = divmod(amount_cents, len(member_ids))
    return {
        member_id: base + (1 if index < remainder else 0)
        for index, member_id in enumerate(member_ids)
    }


def compute_balances(member_ids, expenses, settlements):
    """
    Net balance per member in cents: positive means the group owes them,
    negative means they owe the group.

    expenses: iterable of (paid_by_id, amount_cents, {member_id: share_cents})
    settlements: iterable of (from_member_id, to_member_id, amount_cents)
    """
    balances = {member_id: 0 for member_id in member_ids}
    for paid_by_id, amount_cents, shares in expenses:
        balances[paid_by_id] += amount_cents
        for member_id, share_cents in shares.items():
            balances[member_id] -= share_cents
    for from_member_id, to_member_id, amount_cents in settlements:
        # Paying someone back raises your balance and lowers theirs.
        balances[from_member_id] += amount_cents
        balances[to_member_id] -= amount_cents
    return balances


def simplify_debts(balances):
    """
    Turn net balances into a short list of payments that settles everyone.

    Greedy: sort debtors and creditors largest first, then walk both lists,
    each payment fully clearing at least one of the pair. Every payment
    retires a person, so there are at most n - 1 payments.

    Returns a list of (from_member_id, to_member_id, amount_cents).
    """
    debtors = sorted(
        ([member_id, -balance] for member_id, balance in balances.items() if balance < 0),
        key=lambda item: (-item[1], item[0]),
    )
    creditors = sorted(
        ([member_id, balance] for member_id, balance in balances.items() if balance > 0),
        key=lambda item: (-item[1], item[0]),
    )

    payments = []
    debtor_index = creditor_index = 0
    while debtor_index < len(debtors) and creditor_index < len(creditors):
        debtor = debtors[debtor_index]
        creditor = creditors[creditor_index]
        amount = min(debtor[1], creditor[1])
        payments.append((debtor[0], creditor[0], amount))
        debtor[1] -= amount
        creditor[1] -= amount
        if debtor[1] == 0:
            debtor_index += 1
        if creditor[1] == 0:
            creditor_index += 1
    return payments
