"""Generic parser for role-tagged spoken scripts."""

from dataclasses import dataclass
import html
import re
from typing import Iterable, List, Optional


@dataclass(frozen=True)
class RoleLine:
    """One spoken line from a role-tagged script."""

    role: str
    text: str
    style: Optional[str] = None


class RoleScriptParseError(ValueError):
    """Raised when a role-tagged script contains malformed role blocks."""


_TAG_RE = re.compile(
    r"<\s*(?P<close>/)?\s*(?P<role>[A-Za-z][\w-]*)\b(?P<attrs>[^>]*)>",
    re.DOTALL,
)
_STYLE_RE = re.compile(r"""\bstyle\s*=\s*(['"])(?P<style>.*?)\1""", re.DOTALL)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


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

    lines: list[RoleLine] = []
    stack: list[dict[str, object]] = []
    cleaned_script = _COMMENT_RE.sub("", script)

    for match in _TAG_RE.finditer(cleaned_script):
        role = match.group("role").upper()
        raw_role = match.group("role")
        is_close = bool(match.group("close"))
        attrs = match.group("attrs") or ""

        if is_close:
            if attrs.strip():
                raise RoleScriptParseError(f"Closing tag {raw_role!r} cannot have attributes")
            if not stack:
                raise RoleScriptParseError(f"Unexpected closing role tag </{raw_role}>")
            opening = stack.pop()
            opening_role = str(opening["role"])
            if opening_role != role:
                raise RoleScriptParseError(
                    f"Mismatched role tag: opened <{opening_role}> but closed </{raw_role}>"
                )

            text = cleaned_script[int(opening["content_start"]): match.start()]
            if _contains_role_tag(text):
                raise RoleScriptParseError(
                    f"Nested role tags are not supported inside <{opening_role}>"
                )
            if allowed_roles is not None and opening_role not in allowed_roles:
                continue

            normalized_text = " ".join(html.unescape(text).split()).strip()
            if not normalized_text:
                continue
            lines.append(
                RoleLine(
                    role=opening_role,
                    text=normalized_text,
                    style=str(opening["style"]) or None,
                )
            )
            continue

        if stack:
            raise RoleScriptParseError(
                f"Nested role tag <{raw_role}> inside <{stack[-1]['role']}>"
            )

        style_match = _validate_role_attrs(role, attrs)
        style = style_match.group("style").strip() if style_match else None
        stack.append(
            {
                "role": role,
                "style": html.unescape(style or "").strip(),
                "content_start": match.end(),
            }
        )

    if stack:
        opening_role = str(stack[-1]["role"])
        raise RoleScriptParseError(f"Unclosed role tag <{opening_role}>")

    return lines


def _validate_role_attrs(role: str, attrs: str) -> re.Match[str] | None:
    attrs = attrs.strip()
    if not attrs:
        return None
    style_match = _STYLE_RE.search(attrs)
    if style_match is None and re.search(r"\bstyle\s*=", attrs):
        raise RoleScriptParseError(
            f"Malformed style attribute on <{role}>"
        )
    return style_match


def _contains_role_tag(text: str) -> bool:
    return bool(_TAG_RE.search(text))
