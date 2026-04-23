#!/usr/bin/env python3
"""
scripts/bluesky.py - Save a Bluesky post as markdown with images.

Usage:
  python scripts/bluesky.py <bsky-url>

Saves images to ~/todo/img/ and prints markdown for pasting into log_YYYY.md.
"""

import sys, re, json, urllib.request, urllib.parse, subprocess, argparse
from datetime import datetime
from pathlib import Path

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


def save_external_thumb(external, slug, rkey_prefix):
    """Download thumbnail from an external link card. Returns [(path, alt)] or []."""
    thumb_url = external.get("thumb", "")
    if not thumb_url:
        return []
    fname = f"{slug}_{rkey_prefix}_thumb.png"
    dest = IMG_DIR / fname
    download_and_convert(thumb_url, dest)
    print(f"  saved {dest.name}", file=sys.stderr)
    alt = external.get("title", "") or ""
    return [(f"img/{fname}", alt)]


def format_external_card(external, images):
    """Render an external link card as markdown."""
    uri = external.get("uri", "")
    title = external.get("title", "") or uri
    description = external.get("description", "")
    lines = [f"[{title}]({uri})"]
    if description:
        lines.append(f"> {description}")
    for img_path, img_alt in images:
        label = img_alt or title
        lines.append(f"![{label}]({img_path})")
    return "\n".join(lines)


def extract_images_from_embeds(embeds, slug, rkey_prefix):
    for embed in embeds:
        etype = embed.get("$type", "")
        if etype.startswith("app.bsky.embed.images"):
            return save_images(embed.get("images", []), slug, rkey_prefix)
        elif etype.startswith("app.bsky.embed.external"):
            return save_external_thumb(embed.get("external", {}), slug, rkey_prefix)
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
    q_date = format_date(q_value.get("createdAt", embed_record.get("indexedAt", "")))

    # Images or external card inside the quoted post
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

    # Link back to the original quoted post
    if q_url:
        lines.append(">")
        date_label = q_date if q_date else "post"
        lines.append(f"> 🦋 [{date_label}]({q_url})")

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
    external_card = ""
    quote_block = ""
    quote_images = []

    if etype.startswith("app.bsky.embed.images"):
        main_images = save_images(embed.get("images", []), slug, rkey_prefix)

    elif etype.startswith("app.bsky.embed.external"):
        external = embed.get("external", {})
        main_images = save_external_thumb(external, slug, rkey_prefix)
        external_card = format_external_card(external, main_images)

    elif etype.startswith("app.bsky.embed.recordWithMedia"):
        # Quote post + media (images or external link card) on main post
        media = embed.get("media", {})
        mtype = media.get("$type", "")
        if mtype.startswith("app.bsky.embed.images"):
            main_images = save_images(media.get("images", []), slug, rkey_prefix)
        elif mtype.startswith("app.bsky.embed.external"):
            external = media.get("external", {})
            main_images = save_external_thumb(external, slug, rkey_prefix)
            external_card = format_external_card(external, main_images)
        record_wrapper = embed.get("record", {})
        view_record = record_wrapper.get("record", record_wrapper)
        quote_block, quote_images, _ = build_quote_block(view_record)

    elif etype.startswith("app.bsky.embed.record"):
        # Pure quote post (no media attached to main post)
        view_record = embed.get("record", {})
        quote_block, quote_images, _ = build_quote_block(view_record)

    # Assemble markdown
    parts = [
        f"**{display}** ([@{handle}](https://bsky.app/profile/{handle}))",
        "",
        text,
    ]

    if external_card:
        parts.append("")
        parts.append(external_card)

    if quote_block:
        parts.append("")
        parts.append(quote_block)

    parts.extend([
        "",
        f"🦋 [{date_str}]({post_url})",
    ])

    result = "\n".join(parts)

    # Append standalone image references for non-external main images
    if main_images and not external_card:
        result += "\n\n"
        for img_path, img_alt in main_images:
            label = img_alt or img_path.split("/")[-1].rsplit(".", 1)[0]
            result += f"![{label}]({img_path})\n"

    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("url", help="Bluesky post URL")
    parser.add_argument("--commonplace", action="store_true",
                        help="Save images to ~/todo/commonplace/img/ instead of ~/todo/img/")
    args = parser.parse_args()

    global IMG_DIR
    if args.commonplace:
        IMG_DIR = Path.home() / "todo" / "commonplace" / "img"
    else:
        IMG_DIR = Path.home() / "todo" / "img"

    IMG_DIR.mkdir(parents=True, exist_ok=True)

    at_uri = extract_at_uri(args.url)
    print(f"Fetching {at_uri}", file=sys.stderr)
    post = fetch_post(at_uri)
    author_handle = post["author"].get("handle", "")
    rkey = post["uri"].split("/")[-1]
    print(f"Post by @{author_handle}", file=sys.stderr)

    if args.commonplace:
        date_str = datetime.now().strftime("%Y-%m-%d")
        slug = handle_slug(author_handle)
        rkey_prefix = rkey[:8]
        suggested_filename = f"{date_str}_{slug}-{rkey_prefix}.md"
        print(f"# FILENAME: {suggested_filename}", file=sys.stderr)

    print(build_markdown(post))


if __name__ == "__main__":
    main()
