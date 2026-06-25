"""Generic parser for role-tagged spoken scripts."""

from dataclasses import dataclass
import re
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class RoleLine:
    """One spoken line from a role-tagged script."""

    role: str
    text: str
    style: Optional[str] = None


_ROLE_BLOCK_RE = re.compile(
    r"<\s*(?P<role>[A-Za-z][\w-]*)\b(?P<attrs>[^>]*)>"
    r"(?P<text>.*?)"
    r"</\s*(?P=role)\s*>",
    re.DOTALL,
)
_STYLE_RE = re.compile(r"""\bstyle\s*=\s*(['"])(?P<style>.*?)\1""", re.DOTALL)


def parse_role_script(
    script: str, role_tags: Optional[Iterable[str]] = None
) -> List[RoleLine]:
    """
    Parse ordered role-tagged script blocks.

    Example:
        <HOST>text</HOST><SYSTEM style="hostile">text</SYSTEM>
    """
    if not script:
        return []

    allowed_roles = None
    if role_tags is not None:
        allowed_roles = {role.upper() for role in role_tags}

    lines = []
    for match in _ROLE_BLOCK_RE.finditer(script):
        role = match.group("role").upper()
        if allowed_roles is not None and role not in allowed_roles:
            continue

        text = " ".join(match.group("text").split()).strip()
        if not text:
            continue

        style_match = _STYLE_RE.search(match.group("attrs") or "")
        style = style_match.group("style").strip() if style_match else None
        lines.append(RoleLine(role=role, text=text, style=style or None))

    return lines
