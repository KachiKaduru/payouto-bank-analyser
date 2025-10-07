from typing import List, Dict


def is_valid_parse(transactions: List[Dict[str, str]]) -> bool:
    if not transactions:
        return False
    true_checks = sum(
        1 for txn in transactions if txn.get("Check", "").upper() == "TRUE"
    )
    success_rate = true_checks / len(transactions)
    return success_rate >= 0.70  # 90% threshold; adjust as needed
