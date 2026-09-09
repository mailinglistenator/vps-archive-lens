#!/usr/bin/env python3
"""
VPS Archive Lens - User Management CLI
Allows administrators to add, list, revoke, and manage user access tokens.
"""

import sys
import os
import argparse
from pathlib import Path
try:
    from dotenv import load_dotenv
    PROJECT_ROOT = Path(__file__).resolve().parent.parent
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ensure server package can be imported
sys.path.insert(0, str(PROJECT_ROOT))
from server.users import UserManager

def get_base_url() -> str:
    return os.getenv("BASE_URL", "http://localhost:8888").rstrip("/")

def main():
    parser = argparse.ArgumentParser(
        description="VPS Archive Lens - Multi-User Management CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 server/manage_users.py add alice
  python3 server/manage_users.py add bob --role user
  python3 server/manage_users.py add charlie --token custom_secret_key_123
  python3 server/manage_users.py list
  python3 server/manage_users.py revoke bob
"""
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Command: add
    parser_add = subparsers.add_parser("add", help="Add or update a user access token")
    parser_add.add_argument("username", help="Username for the new user (e.g. 'alice', 'bob')")
    parser_add.add_argument("--role", choices=["user", "admin"], default="user", help="User role (default: user)")
    parser_add.add_argument("--token", default=None, help="Custom secret token (randomly generated if omitted)")

    # Command: list
    subparsers.add_parser("list", help="List all registered users and roles")

    # Command: revoke
    parser_revoke = subparsers.add_parser("revoke", help="Revoke a user access token")
    parser_revoke.add_argument("username", help="Username of the user to revoke")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    storage_dir = Path(os.getenv("STORAGE_DIR", PROJECT_ROOT / "snapshots"))
    manager = UserManager(storage_dir=storage_dir)
    base_url = get_base_url()

    if args.command == "add":
        try:
            user = manager.add_user(args.username, role=args.role, custom_token=args.token)
            print("\n" + "=" * 60)
            print(f"🎉 User '{user.username}' successfully configured!")
            print("=" * 60)
            print(f"👤 Username:    {user.username}")
            print(f"🛡️  Role:        {user.role}")
            print(f"🔑 Secret Token: {user.token}")
            print(f"🌐 VPS Endpoint: {base_url}")
            print("\n📋 Send this snippet to your friend to set up their browser extension:\n")
            print("  1. Download the extension from GitHub:")
            print("     Repo: https://github.com/mailinglistenator/vps-archive-lens")
            print("     Direct Zip: https://github.com/mailinglistenator/vps-archive-lens/archive/refs/heads/main.zip\n")
            print("  2. Load into Chrome / Brave / Edge:")
            print("     Open chrome://extensions (or edge://extensions) -> Toggle 'Developer mode' -> 'Load unpacked' -> Select 'extension' folder\n")
            print(f"  3. In Extension Settings, set:")
            print(f"     - VPS Archiver URL: {base_url}")
            print(f"     - Secret API Token: {user.token}")
            print("  4. Click 'Save Settings' and you're ready to archive!\n")
            print("=" * 60 + "\n")
        except Exception as e:
            print(f"❌ Error adding user: {e}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list":
        users = manager.list_users()
        if not users:
            print("\nNo users registered yet. Run 'manage_users.py add <username>' to create one.\n")
            return

        print("\n" + "=" * 76)
        print(f"{'USERNAME':<16} {'ROLE':<8} {'CREATED AT':<22} {'TOKEN'}")
        print("=" * 76)
        for u in sorted(users, key=lambda x: x.username):
            masked_token = u.token[:10] + "..." + u.token[-4:] if len(u.token) > 16 else u.token
            created = u.created_at[:19].replace("T", " ") if u.created_at else "N/A"
            print(f"{u.username:<16} {u.role:<8} {created:<22} {masked_token}")
        print("=" * 76)
        print(f"Total Users: {len(users)}\n")

    elif args.command == "revoke":
        confirm = manager.revoke_user(args.username)
        if confirm:
            print(f"\n✅ User '{args.username}' has been successfully revoked. Their token will no longer work.\n")
        else:
            print(f"\n⚠️ User '{args.username}' not found.\n", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
