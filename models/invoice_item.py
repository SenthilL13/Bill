from dataclasses import dataclass
from typing import List

@dataclass
class InvoiceItem:
    item_name: str
    quantity: float
    rate: float
    
    @property
    def amount(self) -> float:
        return round(self.quantity * self.rate, 2)

def calculate_totals(items: List[InvoiceItem]) -> dict:
    total_amount = sum(item.amount for item in items)
    cgst = round(total_amount * 0.025, 2)
    sgst = round(total_amount * 0.025, 2)
    grand_total = round(total_amount + cgst + sgst, 2)
    
    return {
        'total_amount': total_amount,
        'cgst': cgst,
        'sgst': sgst,
        'grand_total': grand_total
    }