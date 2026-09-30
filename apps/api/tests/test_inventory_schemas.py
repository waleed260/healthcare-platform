from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.modules.inventory.schemas import InventoryAdjustmentCreate, InventoryProductCreate


def test_inventory_product_has_bounded_type_and_minimum() -> None:
    product = InventoryProductCreate(name="Gloves", product_type="consumable", minimum_stock=Decimal("2.500"))
    assert product.minimum_stock == Decimal("2.500")
    with pytest.raises(ValidationError):
        InventoryProductCreate(name="Unknown", product_type="other")


def test_inventory_adjustment_rejects_zero_delta() -> None:
    with pytest.raises(ValidationError):
        InventoryAdjustmentCreate(branch_id=uuid4(), product_id=uuid4(), delta=Decimal("0"), reason="No change")
