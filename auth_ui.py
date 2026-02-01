from supabase_client import supabase_authed
from bootstrap_db import ensure_user_seeded

res = sb.auth.sign_in_with_password({
    "email": email,
    "password": senha
})

sb_user = supabase_authed(res.session.access_token)
ensure_user_seeded(sb_user, res.user.id)

st.session_state["session"] = res.session
st.session_state["user"] = res.user
st.rerun()


