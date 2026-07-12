from __future__ import annotations

from .crm_repository import CRMRepository, utc_now


class CRMIdentityBridge:
    """Links CRM leads with confirmed local identity without exposing PII to LLMs."""

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

    def delete_customer_records(self, *, customer_id: str) -> int:
        """Delete direct and historically session-linked CRM records.

        A lead can be captured before optional face enrollment, so its customer_id
        may initially be NULL. The corresponding conversation session is later
        bound to the customer during enrollment. Querying both columns guarantees
        that a later user deletion request also removes those pre-enrollment leads.
        """
        if not customer_id:
            return 0
        with self.repository._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM sales_leads
                WHERE customer_id = ?
                   OR session_id IN (
                       SELECT session_id
                       FROM conversation_sessions
                       WHERE customer_id = ?
                   )
                """,
                (customer_id, customer_id),
            )
        return int(cursor.rowcount)
