from __future__ import annotations

from .crm_repository import CRMRepository, utc_now


class CRMIdentityBridge:
    """Links a consented Session lead after optional face enrollment.

    A customer may authorize contact before choosing to register face memory. The
    CRM row therefore starts with customer_id=NULL. Once face enrollment succeeds,
    this bridge attaches the already-consented lead to the confirmed local customer
    so a later identity deletion can remove all of that customer's CRM records.
    """

    def __init__(self, repository: CRMRepository) -> None:
        self.repository = repository

    def bind_session(self, *, session_id: str, customer_id: str) -> bool:
        if not session_id or not customer_id:
            return False
        with self.repository._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sales_leads
                SET customer_id = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (customer_id, utc_now(), session_id),
            )
        return cursor.rowcount > 0
