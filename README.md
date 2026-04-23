# rlg Claude Commands

Custom [Claude Code](https://claude.ai/code) slash commands by [@RichGibson](https://github.com/RichGibson).

## Install

```bash
git clone https://github.com/RichGibson/claude-commands ~/.claude/commands/rlg
```

Commands are available immediately in any new Claude Code session as `/rlg:<command>`.

## Requirements

- Python 3
- macOS `sips` (for WebP→PNG conversion, built into macOS)

## Commands

### `/rlg:bluesky <url>`

Fetches a Bluesky post, downloads any images to `~/todo/img/`, and outputs
copy-pasteable markdown formatted like a skeet for pasting into a journal or log file.

**Example:**
```
/rlg:bluesky https://bsky.app/profile/someone.bsky.social/post/abc123
```

**Output includes:**
- Author name and handle linked to their profile
- Post text with links, mentions, and hashtags converted to markdown
- Quoted post text (if any) in a blockquote
- Images downloaded to `~/todo/img/` as PNG with markdown image references
- Butterfly emoji footer linking back to the original post

### `/rlg:commonplace-bluesky <url>`

Fetches a Bluesky post, asks for your reaction, and writes a dated file to `~/todo/commonplace/`. Images go to `~/todo/commonplace/img/`.

After fetching the post it asks: *"Why did you save this? What connected with you?"* — your answer becomes the Reaction section of the commonplace entry. It also suggests links to relevant wiki pages based on the content.

**Example:**
```
/rlg:commonplace-bluesky https://bsky.app/profile/someone.bsky.social/post/abc123
```

**Output file:** `~/todo/commonplace/YYYY-MM-DD_handle-rkey.md`
