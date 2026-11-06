"""Autoria estável do usuário. Registros locais/legados mantêm autoria nula."""
TABLES = {"itinerary_items", "diary_entries", "diary_evidence", "diary_goal_claims"}


def attribute(db, table, row_id, actor_user_id, created=False):
    if table not in TABLES:
        raise ValueError("Tabela de autoria inválida")
    if created:
        db.execute(f"UPDATE {table} SET created_by_user_id=?,updated_by_user_id=? WHERE id=?", (actor_user_id,actor_user_id,row_id))
    else:
        db.execute(f"UPDATE {table} SET updated_by_user_id=? WHERE id=?", (actor_user_id,row_id))
