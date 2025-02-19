import re
import html

from markdown.preprocessors import Preprocessor
from markdown.extensions import Extension

re_discord_emoji = re.compile(r"(<|&lt;)(a?):([^:]+):(\d+)(&gt;|>)(?:&gt;|>)")

urlfinder = re.compile(
    r"((([A-Za-z]{3,9}:(?:\/\/)?)(?:[\-;:&=\+\$,\w]+@)?[A-Za-z0-9\.\-]+(:[0-9]+)?|"
    r"(?:www\.|[\-;:&=\+\$,\w]+@)[A-Za-z0-9\.\-]+)((?:/[\+~%/\.\w\-_]*)?\??"
    r"(?:[\-\+=&;%@\.\w_]*)#?(?:[\.!/\\\w]*))?)"
)


class URLify(Preprocessor):
    def run(self, lines):
        return [
            urlfinder.sub(r"<\1>", line)
            for line in lines
        ]


class URLifyExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(URLify(md), "urlify", 999)


class SmallLinePreprocessor(Preprocessor):
    def run(self, lines):
        new_lines = []
        for line in lines:
            # If the line starts with '-#', wrap it with <small> tags
            if line.strip().startswith("-#"):
                line = f"<small>{line[2:].strip()}</small>"
            new_lines.append(line)
        return new_lines


class DiscordEmojiProcessor(Preprocessor):
    def run(self, lines):
        new_lines = []
        for line in lines:
            line = html.unescape(line)

            # Remove emojis from line to check if it was only emojis
            test_data = re_discord_emoji.sub("", line).strip()
            add_jumbo = " jumboable" if not test_data else ""

            # Replace emojis with img tags
            new_line = re_discord_emoji.sub(lambda m:
                f'<img class="emoji{add_jumbo}" src="https://cdn.discordapp.com/emojis/{m.group(4)}.'
                f'{"gif" if m.group(1) == "a" else "png"}" alt="{m.group(3).replace("<", "")}"/>',
                line
            )

            new_lines.append(new_line)
        return new_lines


class DiscordEmojiExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(DiscordEmojiProcessor(md), "discord_emoji", 175)


class SmallLineExtension(Extension):
    def extendMarkdown(self, md):
        md.preprocessors.register(SmallLinePreprocessor(md), "small_line", 175)
