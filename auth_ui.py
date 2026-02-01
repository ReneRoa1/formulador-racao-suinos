# auth_ui.py
# -*- coding: utf-8 -*-
import streamlit as st
from supabase_client import supabase_anon, supabase_authed
from bootstrap_db import ensure_user_seeded

def auth_gate():
    """
    Mostra Login / Criar conta e retorna user_id quando autenticado.
    Guarda session/user em st.session_state.
    """
    sb = supabase_anon()

    if "session" not in st.session_state:
        st.session_state["session"] = None
        st.session_state["user"] = None

    # Se não estiver logado, mostra login/cadastro e para o app aqui
    if st.session_state["session"] is None:
        st.subheader("Entrar / Criar conta")

        tab_login, tab_signup = st.tabs(["Login", "Criar conta"])

        with tab_login:
            email = st.text_input("Email", key="login_email")
            senha = st.text_input("Senha", type="password", key="login_senha")
            if st.button("Entrar", key="btn_login"):
                try:
                    res = sb.auth.sign_in_with_password({"email": email, "password": senha})

                    # Client autenticado (RLS)
                    sb_user = supabase_authed(res.session.access_token)
                    ensure_user_seeded(sb_user, res.user.id)

                    st.session_state["session"] = res.session
                    st.session_state["user"] = res.user
                    st.rerun()
                except Exception as e:
                    st.error(f"Falha no login: {e}")

        with tab_signup:
            email = st.text_input("Email", key="signup_email")
            senha = st.text_input("Senha", type="password", key="signup_senha")
            if st.button("Criar conta", key="btn_signup"):
                try:
                    sb.auth.sign_up({"email": email, "password": senha})
                    st.success("Conta criada! Agora faça login na aba Login.")
                except Exception as e:
                    st.error(f"Falha ao criar conta: {e}")

        st.stop()

    # Logado
    user = st.session_state["user"]
    st.caption(f"Logado como: {user.email}")

    if st.button("Sair", key="btn_logout"):
        try:
            sb.auth.sign_out()
        except Exception:
            pass
        st.session_state["session"] = None
        st.session_state["user"] = None
        st.rerun()

    return user.id
