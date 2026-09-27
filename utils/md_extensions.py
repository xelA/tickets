import re
import markdown
import markupsafe
import xml.etree.ElementTree as ET

from markdown.blockprocessors import BlockProcessor, HashHeaderProcessor
from markdown.extensions import Extension
from markdown.inlinepatterns import InlineProcessor, SimpleTagInlineProcessor
from markdown.preprocessors import Preprocessor
from markdown.treeprocessors import Treeprocessor
from markdown.util import AtomicString

re_discord_emoji = re.compile(r"<(a?):([A-Za-z0-9_~]+):(\d+)>")
re_unicode_emoji_base = re.compile(r"[🀀-🫿☀-➿]")
re_unicode_emoji = re.compile(
    r"[🀀-🫿☀-➿⬀-⯿←-⇿"
    r"⌀-⏿️‍⃣󠀠-󠁿]"
)
re_mention = re.compile(r"<(@!?|@&|#)(\d+)>")

safe_schemes = ("http://", "https://", "mailto:")


def mention_text(kind: str, snowflake: str, mentions: dict | None) -> str:
    """ Turn a raw <@id>, <@&id> or <#id> into how Discord displays it """
    def lookup(group: str) -> str | None:
        found = (mentions or {}).get(group)
        return str(found[snowflake]) if isinstance(found, dict) and found.get(snowflake) else None

    match kind:
        case "@" | "@!":
            name = lookup("users")
            return f"@{name}" if name else "@unknown-user"
        case "@&":
            name = lookup("roles")
            return f"@{name}" if name else "@unknown-role"
        case _:
            name = lookup("channels")
            return f"#{name}" if name else "#unknown-channel"


def plain_text(text: str | None, mentions: dict | None = None) -> str:
    """ Message text without markup, used for reply previews and meta tags """
    if not text:
        return ""
    text = re_mention.sub(lambda m: mention_text(m.group(1), m.group(2), mentions), str(text))
    text = re_discord_emoji.sub(lambda m: f":{m.group(2)}:", text)
    return " ".join(text.split())


class DiscordEmojiInline(InlineProcessor):
    """ <:name:id> and <a:name:id> custom emojis """

    def handleMatch(self, m, data):  # ruff: ignore[invalid-function-name, unused-method-argument]
        el = ET.Element("img")
        el.set("class", "emoji")
        el.set("src", f"https://cdn.discordapp.com/emojis/{m.group(3)}.{'gif' if m.group(1) else 'png'}")
        el.set("alt", f":{m.group(2)}:")
        el.set("draggable", "false")
        return el, m.start(0), m.end(0)


class MentionInline(InlineProcessor):
    """ User, role and channel mentions as Discord style pills """

    def __init__(self, pattern, md, renderer):
        super().__init__(pattern, md)
        self.renderer = renderer

    def handleMatch(self, m, data):  # ruff: ignore[invalid-function-name, unused-method-argument]
        el = ET.Element("span")
        el.set("class", "mention")
        el.text = AtomicString(
            mention_text(m.group(1), m.group(2), self.renderer.mentions)
        )
        return el, m.start(0), m.end(0)


class SpoilerInline(InlineProcessor):
    """ ||spoiler||, click to reveal """

    def handleMatch(self, m, data):  # ruff: ignore[invalid-function-name, unused-method-argument]
        el = ET.Element("span")
        el.set("class", "spoiler")
        el.text = m.group(1)
        return el, m.start(0), m.end(0)


class BareUrlInline(InlineProcessor):
    """ Discord links plain URLs, markdown does not """

    def handleMatch(self, m, data):  # ruff: ignore[invalid-function-name, unused-method-argument]
        url = m.group(0)
        el = ET.Element("a")
        el.set("href", url)
        el.text = AtomicString(url)
        return el, m.start(0), m.end(0)


class DiscordLinesPreprocessor(Preprocessor):
    """
    Line based Discord syntax markdown does not know

    "-# " lines get their own block (see SubtextBlock), "> " only quotes its own line
    and ">>> " quotes everything after it.
    """

    def run(self, lines):
        new_lines = []
        quote_rest = False
        for line in lines:
            if quote_rest:
                new_lines.append(f"> {line}")
            elif line.startswith(">>> "):
                quote_rest = True
                new_lines.append(f"> {line[4:]}")
            elif line.startswith("-# "):
                new_lines.extend(["", line, ""])
            else:
                if new_lines and new_lines[-1].startswith("> ") and not line.startswith(">"):
                    new_lines.append("")
                new_lines.append(line)
        return new_lines


class SubtextBlock(BlockProcessor):
    """ "-# text" is Discord's small grey subtext """

    def test(self, parent, block):  # ruff: ignore[unused-method-argument]
        return block.startswith("-# ")

    def run(self, parent, blocks):
        block = blocks.pop(0)
        el = ET.SubElement(parent, "small")
        el.set("class", "subtext")
        el.text = block[3:].strip()


class DiscordHeaderProcessor(HashHeaderProcessor):
    """ Discord only has # to ###, and needs a space after the hashes """

    RE = re.compile(r"(?:^|\n)(?P<level>#{1,3}) (?P<header>(?:\\.|[^\\])*?)#*(?:\n|$)")


class SanitizeTree(Treeprocessor):
    """ Drop anything that could run script, links must be http(s) or mailto """

    def run(self, root):
        for el in root.iter():
            if el.tag == "a":
                href = el.get("href", "")
                if not href.lower().startswith(safe_schemes):
                    el.attrib.pop("href", None)
                else:
                    el.set("target", "_blank")
                    el.set("rel", "noopener noreferrer nofollow")
            elif el.tag == "img" and el.get("class") != "emoji":
                # Discord does not render markdown images, show the alt text instead
                el.tag = "span"
                el.text = el.attrib.pop("alt", "")
                el.attrib.clear()


class DiscordExtension(Extension):
    def __init__(self, renderer, **kwargs):
        self.renderer = renderer
        super().__init__(**kwargs)

    def extendMarkdown(self, md):  # ruff: ignore[invalid-function-name]
        # Raw HTML is never allowed, it's escaped and shown as text instead
        md.preprocessors.deregister("html_block")
        md.inlinePatterns.deregister("html")

        # Markdown features Discord does not have
        for name in ("code", "setextheader", "hr", "reference", "indent"):
            md.parser.blockprocessors.deregister(name)
        for name in ("reference", "image_reference", "short_reference", "short_image_ref"):
            md.inlinePatterns.deregister(name)
        md.parser.blockprocessors.register(DiscordHeaderProcessor(md.parser), "hashheader", 70)

        # Discord only syntax
        md.preprocessors.register(DiscordLinesPreprocessor(md), "discord_lines", 15)
        md.parser.blockprocessors.register(SubtextBlock(md.parser), "subtext", 75)
        md.inlinePatterns.register(DiscordEmojiInline(re_discord_emoji.pattern, md), "discord_emoji", 175)
        md.inlinePatterns.register(MentionInline(re_mention.pattern, md, self.renderer), "mention", 174)
        md.inlinePatterns.register(BareUrlInline(r"https?://[^\s<>]*[^\s<>.,:;\"')\]!?*_~|]", md), "bare_url", 115)
        md.inlinePatterns.register(SpoilerInline(r"\|\|(.+?)\|\|", md), "spoiler", 66)
        md.inlinePatterns.register(SimpleTagInlineProcessor(r"(~~)(.+?)~~", "del"), "strike", 65)

        # __underline__ instead of bold, _italic_ still works
        md.inlinePatterns.deregister("em_strong2")
        md.inlinePatterns.register(SimpleTagInlineProcessor(r"(__)(.+?)__", "u"), "underline", 50)
        md.inlinePatterns.register(SimpleTagInlineProcessor(r"(?<![\w_])(_)(?!_)(.+?)(?<!_)_(?![\w_])", "em"), "em_underscore", 49)

        md.treeprocessors.register(SanitizeTree(md), "sanitize", 1)


class DiscordMarkdown:
    """ Renders Discord message markdown to safe HTML """

    def __init__(self):
        self.mentions: dict | None = None
        self.md = markdown.Markdown(
            extensions=["fenced_code", "sane_lists", DiscordExtension(self)]
        )

    @staticmethod
    def is_jumbo(text: str) -> bool:
        """ Discord shows messages that only contain (up to 30) emojis bigger """
        custom = len(re_discord_emoji.findall(text))
        rest = re_discord_emoji.sub("", text)
        unicode_count = len(re_unicode_emoji_base.findall(rest))
        leftover = re_unicode_emoji.sub("", rest).strip()
        return not leftover and 0 < custom + unicode_count <= 30

    def render(self, text, mentions: dict | None = None) -> markupsafe.Markup:
        if text is None or text == "":
            return markupsafe.Markup("")

        text = str(text)
        self.mentions = mentions
        self.md.reset()
        html = self.md.convert(text)
        self.mentions = None

        classes = "markdown jumbo" if self.is_jumbo(text) else "markdown"
        return markupsafe.Markup(f'<div class="{classes}">{html}</div>')
