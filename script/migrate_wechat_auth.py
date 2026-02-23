#!/usr/bin/env python3
from core.db import DB
from core.wechat_auth_service import migrate_global_auth_to_owner


def main():
    session = DB.get_session()
    result = migrate_global_auth_to_owner(session, owner_id="admin", overwrite=False)
    print(result)


if __name__ == "__main__":
    main()
