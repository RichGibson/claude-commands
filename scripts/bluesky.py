#!/usr/bin/env python3
"""
scripts/bluesky.py - Save a Bluesky post as markdown with images.

Usage:
  python scripts/bluesky.py <bsky-url>

Saves images to ~/todo/img/ and prints markdown for pasting into log_YYYY.md.
"""

import sys, re, json, urllib.request, urllib.parse, subprocess
from datetime import datetime
from pathlib import Path

IMG_DIR = Path.home() / "todo" / "img"
BSKY_API = "https://public.api.bsky.app/xrpc"


def resolve_handle(handle):
    url = f"{BSKY_API}/com.atproto.identity.resolveHandle?handle={urllib.parse.quote(handle)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"})) as r:
        return json.loads(r.read())["did"]


def extract_at_uri(raw):
    raw = raw.strip()
    if raw.startswith("at://"):
        return raw
    m = re.search(r'bsky\.app/profile/([^/?\s"]+)/post/([^/?\s"&]+)', raw)
    if not m:
        raise ValueError(f"Cannot parse Bluesky URL: {raw}")
    actor, rkey = m.group(1), m.group(2)
    if not actor.startswith("did:"):
        actor = resolve_handle(actor)
    return f"at://{actor}/app.bsky.feed.post/{rkey}"


def fetch_post(at_uri):
    url = f"{BSKY_API}/app.bsky.feed.getPosts?uris={urllib.parse.quote(at_uri)}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"Accept": "application/json"})) as r:
        data = json.loads(r.read())
    posts = data.get("posts", [])
    if not posts:
        raise ValueError(f"No post found: {at_uri}")
    return posts[0]


def handle_slug(handle):
    return handle.split(".")[0]


def download_and_convert(url, dest):
    if dest.exists():
        return
    req = urllib.request.Request(url, headers={"User-Agent": "bluesky-journal/1.0"})
    with urllib.request.urlopen(req) as r:
        dest.write_bytes(r.read())
    # Convert WebP to PNG (Bluesky CDN serves WebP)
    result = subprocess.run(["file", str(dest)], capture_output=True, text=True)
    if "Web/P" in result.stdout or "RIFF" in result.stdout:
        subprocess.run(
            ["sips", "-s", "format", "png", str(dest), "--out", str(dest)],
            capture_output=True,
        )


def save_images(images, slug, rkey_prefix):
    """Returns [(relative_path_str, alt_text), ...]"""
    saved = []
    for i, img in enumerate(images):
        img_url = img.get("fullsize") or img.get("thumb", "")
        if not img_url:
            continue
        fname = f"{slug}_{rkey_prefix}_{i}.png"
        dest = IMG_DIR / fname
        download_and_convert(img_url, dest)
        print(f"  saved {dest.name}", file=sys.stderr)
        saved.append((f"img/{fname}", img.get("alt", "")))
    return saved


def linkify_md(text, facets):
    """Apply facets to text, converting links/mentions/tags to markdown syntax.
    Facets use UTF-8 byte offsets, not character offsets."""
    if not facets:
        return text

    encoded = text.encode("utf-8")
    spans = []
    for facet in facets:
        start = facet.get("index", {}).get("byteStart", 0)
        end = facet.get("index", {}).get("byteEnd", 0)
        for feature in facet.get("features", []):
            ftype = feature.get("$type", "")
            if ftype == "app.bsky.richtext.facet#link":
                uri = feature.get("uri", "")
                # Use full URL as display text so it's visible when pasted
                spans.append((start, end, uri, uri))
            elif ftype == "app.bsky.richtext.facet#mention":
                did = feature.get("did", "")
                spans.append((start, end, f"https://bsky.app/profile/{did}", None))
            elif ftype == "app.bsky.richtext.facet#tag":
                tag = feature.get("tag", "")
                spans.append((start, end, f"https://bsky.app/hashtag/{tag}", None))

    if not spans:
        return text

    spans.sort(key=lambda x: x[0])
    result = []
    pos = 0
    for start, end, url, display in spans:
        if start > pos:
            result.append(encoded[pos:start].decode("utf-8"))
        chunk = display if display is not None else encoded[start:end].decode("utf-8")
        result.append(f"[{chunk}]({url})")
        pos = end
    if pos < len(encoded):
        result.append(encoded[pos:].decode("utf-8"))
    return "".join(result)


def format_date(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%B %-d, %Y")
    except Exception:
        return iso


def extract_images_from_embeds(embeds, slug, rkey_prefix):
    for embed in embeds:
        if embed.get("$type", "").startswith("app.bsky.embed.images"):
            return save_images(embed.get("images", []), slug, rkey_prefix)
    return []


def build_quote_block(embed_record):
    """Build the > quoted block from an embed.record#viewRecord."""
    q_author = embed_record.get("author", {})
    q_handle = q_author.get("handle", "")
    q_display = q_author.get("displayName") or q_handle
    q_value = embed_record.get("value", {})
    q_text = linkify_md(q_value.get("text", ""), q_value.get("facets", []))
    q_uri = embed_record.get("uri", "")
    q_rkey = q_uri.split("/")[-1] if q_uri else ""
    q_rkey_prefix = q_rkey[:8] if q_rkey else "quote"
    q_slug = handle_slug(q_handle) if q_handle else "quote"
    q_url = f"https://bsky.app/profile/{q_handle}/post/{q_rkey}" if q_handle and q_rkey else ""

    # Images inside the quoted post
    q_images = extract_images_from_embeds(embed_record.get("embeds", []), q_slug, q_rkey_prefix)

    lines = []
    if q_display or q_handle:
        author_md = f"**{q_display}**"
        if q_handle:
            author_md += f" ([@{q_handle}](https://bsky.app/profile/{q_handle}))"
        lines.append(f"> {author_md}")
        lines.append(">")

    for line in q_text.split("\n"):
        lines.append(f"> {line}")

    for img_path, img_alt in q_images:
        label = img_alt or img_path.split("/")[-1].rsplit(".", 1)[0]
        lines.append(f"> ![{label}]({img_path})")

    return "\n".join(lines), q_images, q_url


def build_markdown(post):
    author = post["author"]
    record = post["record"]
    handle = author.get("handle", "")
    display = author.get("displayName") or handle
    text = linkify_md(record.get("text", ""), record.get("facets", []))
    rkey = post["uri"].split("/")[-1]
    rkey_prefix = rkey[:8]
    post_url = f"https://bsky.app/profile/{handle}/post/{rkey}"
    date_str = format_date(record.get("createdAt", ""))
    slug = handle_slug(handle)

    embed = post.get("embed", {})
    etype = embed.get("$type", "")

    main_images = []
    quote_block = ""
    quote_images = []

    if etype.startswith("app.bsky.embed.images"):
        main_images = save_images(embed.get("images", []), slug, rkey_prefix)

    elif etype.startswith("app.bsky.embed.record"):
        # Pure quote post (no media attached to main post)
        # embed.record is the viewRecord of the quoted post
        view_record = embed.get("record", {})
        quote_block, quote_images, _ = build_quote_block(view_record)

    elif etype.startswith("app.bsky.embed.recordWithMedia"):
        # Quote post + images on main post
        media = embed.get("media", {})
        if media.get("$type", "").startswith("app.bsky.embed.images"):
            main_images = save_images(media.get("images", []), slug, rkey_prefix)
        # The nested record wrapper: embed.record.$type = "app.bsky.embed.record#view"
        record_wrapper = embed.get("record", {})
        view_record = record_wrapper.get("record", record_wrapper)
        quote_block, quote_images, _ = build_quote_block(view_record)

    # Assemble markdown
    parts = [
        f"**{display}** ([@{handle}](https://bsky.app/profile/{handle}))",
        "",
        text,
    ]

    if quote_block:
        parts.append("")
        parts.append(quote_block)

    parts.extend([
        "",
        f"🦋 [{date_str}]({post_url})",
    ])

    result = "\n".join(parts)

    # Append standalone image references for main post images
    if main_images:
        result += "\n\n"
        for img_path, img_alt in main_images:
            label = img_alt or img_path.split("/")[-1].rsplit(".", 1)[0]
            result += f"![{label}]({img_path})\n"

    return result


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    url = sys.argv[1]
    at_uri = extract_at_uri(url)
    print(f"Fetching {at_uri}", file=sys.stderr)
    post = fetch_post(at_uri)
    author_handle = post["author"].get("handle", "")
    print(f"Post by @{author_handle}", file=sys.stderr)
    print(build_markdown(post))


if __name__ == "__main__":
    main()
