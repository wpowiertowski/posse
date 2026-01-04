"""POSSE (Publish Own Site, Syndicate Elsewhere) Package.

This package provides the core functionality for the POSSE system,
which synchronizes Ghost blog posts with social media platforms
like Mastodon and Bluesky.

The package currently includes a simple hello world implementation
that serves as the foundation for the syndication system.

Exported Functions:
    hello: Returns a greeting message
    main: Entry point for the posse console command
"""
from .posse import main

__all__ = ["main"]
