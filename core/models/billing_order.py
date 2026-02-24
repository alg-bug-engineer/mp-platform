from .base import Base, Column, String, DateTime, Integer, Text


class BillingOrder(Base):
    __tablename__ = "billing_orders"

    id = Column(String(255), primary_key=True, index=True)
    order_no = Column(String(64), unique=True, index=True, nullable=False)
    owner_id = Column(String(50), index=True, nullable=False)
    plan_tier = Column(String(20), index=True, nullable=False)
    months = Column(Integer, nullable=False, default=1)
    amount_cents = Column(Integer, nullable=False, default=0)
    currency = Column(String(16), nullable=False, default="CNY")
    channel = Column(String(32), nullable=False, default="sandbox")
    status = Column(String(32), nullable=False, default="pending")
    paid_at = Column(DateTime, nullable=True)
    effective_from = Column(DateTime, nullable=True)
    effective_to = Column(DateTime, nullable=True)
    provider_txn_id = Column(String(128), nullable=True)
    provider_payload = Column(Text, nullable=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
