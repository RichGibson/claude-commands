Fetch a Bluesky post and save it to the commonplace with your reaction.

Steps:
1. Run the script and capture the output:
   !`python ~/.claude/commands/rlg/scripts/bluesky.py --commonplace $ARGUMENTS 2>&1`

2. Display the formatted post to the user (not in a code block — render it).

3. Ask the user exactly this question:
   "Why did you save this? What connected with you? (Reply over as many messages as you want — type 'done' when finished.)"

4. Collect their response across one or more messages until they send a message that is exactly "done" or ends with the word "done" on its own line. Concatenate all their messages (excluding the final "done") as the reaction text. Do not proceed until they signal done.

5. Parse the FILENAME line from the stderr output (it looks like `# FILENAME: 2026-04-23_handle-rkey.md`). Use that as the filename.

6. Write the file to ~/todo/commonplace/<filename> using this format:

```
# <display name of author> — <first 8 words of post text>

**Source:** [@<handle>](<post url>)
**Date:** <post date>
**Captured:** <today's date YYYY-MM-DD>

---

<the full formatted post markdown, exactly as output by the script>

---

## Reaction

<the user's response verbatim>

## Links

<suggest 1-3 links to relevant wiki pages in ~/todo/wiki/ based on the content and reaction — use relative paths from commonplace/, e.g. ../wiki/themes/whatever.md>
```

7. Confirm: tell the user the file was written and show the full path. Offer to integrate it into the wiki now or later.
