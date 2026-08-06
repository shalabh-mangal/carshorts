---
name: publish-video
description: Publish an owner-approved final to the correct channel, with clean metadata and analytics follow-up.
triggers: publish, upload, youtube, channel, hashtags, go live, release
---
Goal: the right video on the RIGHT channel with honest metadata — and never a
wrong-channel or wrong-brand slip (both have happened; the guards exist for that).

1. PRECONDITION — Gate 2 is the owner's. Publish ONLY a final the owner has
   explicitly approved (watched and said ship). Never publish on your own judgment.

2. Confirm the channel target before anything uploads:
   the channel guard aborts unless the authenticated channel is carsInShorts
   (CARSHORTS_CHANNEL pins the exact id). If auth is stale, the OWNER runs the
   re-auth / `gh`/YouTube login — you never enter credentials or tokens.

3. Clean the metadata: hashtags must reference ONLY brands actually in the video
   (the cleaner drops wrong-brand tags, including compound ones like #HondaElevate).

4. Publish:
   `carshorts publish <slug> ...`   (asserts the channel guard before insert)

5. AFTER publish — close the loop:
   `carshorts analytics` to fetch fresh numbers once data lands, and remind the
   owner of the two manual YouTube-Studio tasks: pin the rivalry-poll comment and
   set the thumbnail.

Gate: wrong channel or unapproved final = do not publish. Uploading, accepting
terms, and entering credentials are owner/irreversible actions — never automate them.
