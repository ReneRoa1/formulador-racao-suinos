import os
from supabase import create_client

def supabase_anon():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])

def supabase_authed(access_token: str):
    sb = supabase_anon()
    # injeta o JWT do usuário (RLS passa a funcionar)
    sb.postgrest.auth(access_token)
    return sb

from supabase_client import supabase_authed
from bootstrap_db import ensure_user_seeded

sb_user = supabase_authed(res.session.access_token)
ensure_user_seeded(sb_user, res.user.id)

from supabase_client import supabase_authed
from bootstrap_db import ensure_user_seeded

sb_user = supabase_authed(res.session.access_token)
ensure_user_seeded(sb_user, res.user.id)

