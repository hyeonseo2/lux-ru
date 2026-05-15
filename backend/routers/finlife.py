"""FinLife products API router."""
from __future__ import annotations

from fastapi import APIRouter

from ..seed_data import FINLIFE_PRODUCTS

router = APIRouter(prefix="/api/finlife", tags=["finlife"])


@router.get("/deposits")
async def get_deposits():
    """Get deposit products."""
    products = [p.model_dump() for p in FINLIFE_PRODUCTS if p.product_type == "deposit"]
    return {"products": products}


@router.get("/savings")
async def get_savings():
    """Get savings products."""
    products = [p.model_dump() for p in FINLIFE_PRODUCTS if p.product_type == "saving"]
    return {"products": products}


@router.get("/pension")
async def get_pension():
    """Get pension products."""
    products = [p.model_dump() for p in FINLIFE_PRODUCTS if p.product_type == "pension"]
    return {"products": products}


@router.get("/all")
async def get_all_products():
    """Get all FinLife products."""
    return {"products": [p.model_dump() for p in FINLIFE_PRODUCTS]}
