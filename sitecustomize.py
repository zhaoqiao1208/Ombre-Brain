"""
Auto-loaded by Python at startup.
Installs Supabase sync hook on GatewayStateStore.record_conversation_turn
so every successful Gateway chat turn is mirrored to Supabase chat_messages.
"""
import sys

try:
    import gateway_state
    import supabase_sync

    _original_record_turn = gateway_state.GatewayStateStore.record_conversation_turn

    def _patched_record_turn(self, *, profile_id, session_id, round_id, user_text,
                             assistant_text="", model="", client="", route="",
                             created_at=None, max_entries=500):
        # 1. Call the original method (stores in local SQLite)
        turn_id = _original_record_turn(
            self,
            profile_id=profile_id,
            session_id=session_id,
            round_id=round_id,
            user_text=user_text,
            assistant_text=assistant_text,
            model=model,
            client=client,
            route=route,
            created_at=created_at,
            max_entries=max_entries,
        )
        # 2. Mirror to Supabase (non-blocking, fail-soft)
        try:
            supabase_sync.sync_turn(
                user_text=user_text,
                assistant_text=assistant_text,
                conversation_id=session_id,
                assistant_id=profile_id,
            )
        except Exception:
            pass
        return turn_id

    gateway_state.GatewayStateStore.record_conversation_turn = _patched_record_turn
    print("Supabase sync hook installed on GatewayStateStore.record_conversation_turn", file=sys.stderr)
except Exception as exc:
    print(f"sitecustomize: Supabase sync hook skipped: {exc}", file=sys.stderr)
