#!/usr/bin/env python3
"""
Helper script to generate Bluesky session strings.

This script authenticates with Bluesky using your handle and app password,
then exports a session string that can be stored as a Docker secret.

Usage:
    python scripts/get_bluesky_session.py <handle> <password>
    
Example:
    python scripts/get_bluesky_session.py myhandle.bsky.social myapppassword

Security Note:
    - Use app passwords (not your main password) for better security
    - Generate app passwords at: https://bsky.app/settings/app-passwords
    - Keep session strings secure - they provide full account access
    - Session strings expire when you change your password
"""
from atproto import Client
import sys


def main():
    """Generate and display a Bluesky session string."""
    if len(sys.argv) != 3:
        print("Usage: python scripts/get_bluesky_session.py <handle> <password>")
        print("\nExample:")
        print("  python scripts/get_bluesky_session.py myhandle.bsky.social myapppassword")
        print("\nSecurity Tips:")
        print("  - Use an app password, not your main password")
        print("  - Generate app passwords at: https://bsky.app/settings/app-passwords")
        print("  - Keep the session string secure")
        sys.exit(1)

    handle = sys.argv[1]
    password = sys.argv[2]

    try:
        print(f"\n🔄 Authenticating with Bluesky as @{handle}...")
        client = Client()
        profile = client.login(handle, password)
        session_string = client.export_session_string()
        
        print(f"\n✅ Successfully authenticated as @{profile.handle}")
        print(f"   Display Name: {profile.display_name if hasattr(profile, 'display_name') else 'N/A'}")
        print(f"   DID: {profile.did}")
        
        print(f"\n📋 Your session string (save this securely):")
        print("-" * 60)
        print(session_string)
        print("-" * 60)
        
        print(f"\n💾 To save this session string:")
        account_name = handle.split('.')[0]  # Extract handle from domain
        print(f"   mkdir -p secrets")
        print(f"   echo '{session_string}' > secrets/bluesky_{account_name}_access_token.txt")
        
        print(f"\n⚙️  Then add to your config.yml:")
        print(f"""   bluesky:
     accounts:
       - name: "{account_name}"
         instance_url: "https://bsky.social"
         access_token_file: "/run/secrets/bluesky_{account_name}_access_token"
""")
        
        print(f"\n🔒 Security Reminders:")
        print(f"   - This session string provides full access to your account")
        print(f"   - Keep it secure like a password")
        print(f"   - It will expire if you change your password")
        print(f"   - Use app passwords for better security\n")
        
    except Exception as e:
        print(f"\n❌ Authentication failed: {e}")
        print("\nTroubleshooting:")
        print("  - Verify your handle is correct (e.g., yourhandle.bsky.social)")
        print("  - Check your password/app password is correct")
        print("  - Ensure you have internet connectivity")
        print("  - Try using an app password instead of your main password")
        sys.exit(1)


if __name__ == "__main__":
    main()
