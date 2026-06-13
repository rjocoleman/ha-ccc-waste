"""Typed errors raised by the CCC API client.

This module has no Home Assistant imports so the client and its error
handling can be unit tested in isolation.
"""

from __future__ import annotations


class CCCError(Exception):
    """Base error for all CCC client failures."""


class CCCConnectionError(CCCError):
    """The CCC endpoint could not be reached or returned an HTTP error."""


class CCCAddressNotFound(CCCError):
    """The address search returned no matches."""


class CCCPropertyNotFound(CCCError):
    """The property exists but has no kerbside collection."""


class CCCParseError(CCCError):
    """A CCC response did not have the expected structure."""
