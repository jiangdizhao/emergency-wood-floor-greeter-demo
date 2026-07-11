from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from ..models import FlooringProduct, ProductCompareRow


class ProductService:
    def __init__(self) -> None:
        self.data_dir = Path(__file__).resolve().parents[1] / "data"
        self.products_path = self.data_dir / "flooring_products.json"
        self._products: list[FlooringProduct] | None = None

    def list_products(self) -> list[FlooringProduct]:
        if self._products is None:
            self._products = self._load_products()
        return self._products

    def get_product(self, product_id: str) -> FlooringProduct | None:
        return next((p for p in self.list_products() if p.id == product_id), None)

    def resolve_product_reference(self, reference: str) -> list[FlooringProduct]:
        normalized = self._normalize(reference)
        if not normalized:
            return []

        aliases = {
            "spc地板": "spc",
            "石塑地板": "spc",
            "石塑": "spc",
            "多层实木地板": "多层实木",
            "实木复合地板": "多层实木",
            "实木复合": "多层实木",
            "强化地板": "强化",
            "强化复合地板": "强化",
            "强化复合": "强化",
        }
        normalized = aliases.get(normalized, normalized)
        exact: list[FlooringProduct] = []
        fuzzy: list[FlooringProduct] = []
        for product in self.list_products():
            values = {
                self._normalize(product.id),
                self._normalize(product.name),
                self._normalize(product.type),
            }
            if normalized in values:
                exact.append(product)
                continue
            if any(normalized in value or value in normalized for value in values if value):
                fuzzy.append(product)
        return exact or fuzzy

    def resolve_product_references(self, references: Iterable[str]) -> list[FlooringProduct]:
        seen: set[str] = set()
        resolved: list[FlooringProduct] = []
        for reference in references:
            for product in self.resolve_product_reference(reference):
                if product.id not in seen:
                    resolved.append(product)
                    seen.add(product.id)
        return resolved

    def compare_products(self, product_ids: list[str]) -> list[ProductCompareRow]:
        products = [self.get_product(pid) for pid in product_ids]
        products = [p for p in products if p is not None]
        if len(products) < 2:
            return []

        def yes_no(value: bool) -> str:
            return "是" if value else "否"

        rows: list[tuple[str, dict[str, Any]]] = [
            ("产品名称", {p.id: p.name for p in products}),
            ("材质", {p.id: p.type for p in products}),
            ("颜色", {p.id: p.color for p in products}),
            ("风格", {p.id: " / ".join(p.style) for p in products}),
            ("适合空间", {p.id: " / ".join(p.suitable_rooms) for p in products}),
            ("防水", {p.id: yes_no(p.waterproof) for p in products}),
            ("地暖适配", {p.id: yes_no(p.floor_heating) for p in products}),
            ("宠物友好", {p.id: yes_no(p.pet_friendly) for p in products}),
            ("儿童/老人家庭", {p.id: yes_no(p.child_friendly) for p in products}),
            ("耐磨等级", {p.id: p.wear_level for p in products}),
            ("价格区间", {p.id: p.price_range for p in products}),
            ("规格", {p.id: p.spec for p in products}),
            ("核心卖点", {p.id: "；".join(p.selling_points[:3]) for p in products}),
        ]
        return [ProductCompareRow(field=field, values=values) for field, values in rows]

    def _load_products(self) -> list[FlooringProduct]:
        if not self.products_path.exists():
            return []
        with self.products_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return [FlooringProduct.model_validate(item) for item in data]

    @staticmethod
    def _normalize(value: str) -> str:
        return "".join(str(value or "").lower().split())
