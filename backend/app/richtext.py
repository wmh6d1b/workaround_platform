import html
import re
from html.parser import HTMLParser

ALLOWED_TAGS = {'p', 'div', 'br', 'span', 'b', 'strong', 'i', 'em', 'u', 's', 'ul', 'ol', 'li', 'font', 'img'}
VOID_TAGS = {'br', 'img'}
DROP_CONTENT_TAGS = {'script', 'style', 'iframe', 'object', 'embed'}
SAFE_IMAGE = re.compile(r'^data:image/(?:png|jpe?g|gif|webp);base64,[a-z0-9+/=\s]+$', re.I)
SAFE_COLOR = re.compile(r'^(?:#[0-9a-f]{3,8}|[a-z]{1,20}|rgba?\([0-9\s.,%]+\))$', re.I)

class Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth or tag not in ALLOWED_TAGS:
            return
        attributes = dict(attrs)
        if tag == 'img':
            src = attributes.get('src', '')
            if not SAFE_IMAGE.fullmatch(src):
                return
            alt = html.escape(attributes.get('alt', '')[:200], quote=True)
            self.parts.append(f'<img src="{html.escape(src, quote=True)}" alt="{alt}">')
            return
        color = attributes.get('color', '')
        style = attributes.get('style', '')
        match = re.search(r'(?:^|;)\s*color\s*:\s*([^;]+)', style, re.I)
        if match:
            color = match.group(1).strip()
        if SAFE_COLOR.fullmatch(color):
            self.parts.append(f'<{tag} style="color:{color}">')
        else:
            self.parts.append(f'<{tag}>')

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag in ALLOWED_TAGS and tag not in VOID_TAGS and not self.skip_depth:
            self.parts.append(f'</{tag}>')

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif not self.skip_depth and tag in ALLOWED_TAGS and tag not in VOID_TAGS:
            self.parts.append(f'</{tag}>')

    def handle_data(self, data):
        if not self.skip_depth:
            self.parts.append(html.escape(data))

def sanitize_rich_text(value: str | None) -> str:
    if not value:
        return ''
    parser = Sanitizer()
    parser.feed(value)
    parser.close()
    return ''.join(parser.parts).strip()

def rich_text_has_content(value: str) -> bool:
    return '<img ' in value or bool(html.unescape(re.sub(r'<[^>]+>', '', value)).strip())
