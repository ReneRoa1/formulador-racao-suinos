# supabase_client.py
import os
from supabase import create_client
from dotenv import load_dotenv
from pathlib import Path

load_dotenv(dotenv_path=Path(__file__).with_name(".env"))


load_dotenv()

def supabase_anon():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])

def supabase_authed(access_token: str):
    sb = supabase_anon()
    sb.postgrest.auth(access_token)
    return sb
