def ensure_user_seeded(sb, user_id: str):
    # foods
    own = sb.table("foods").select("id").eq("user_id", user_id).limit(1).execute().data
    if not own:
        tpl = sb.table("foods").select("*").is_("user_id", "null").execute().data
        if tpl:
            rows = []
            for r in tpl:
                r.pop("id", None)
                r["user_id"] = user_id
                rows.append(r)
            sb.table("foods").insert(rows).execute()

    # requirements
    own = sb.table("requirements").select("id").eq("user_id", user_id).limit(1).execute().data
    if not own:
        tpl = sb.table("requirements").select("*").is_("user_id", "null").execute().data
        if tpl:
            rows = []
            for r in tpl:
                r.pop("id", None)
                r["user_id"] = user_id
                rows.append(r)
            sb.table("requirements").insert(rows).execute()

