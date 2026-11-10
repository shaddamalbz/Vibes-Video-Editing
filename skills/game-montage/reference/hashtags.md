# Hashtags, YouTube tags and search keywords

Generic platform facts and a research flow. **The channel's own hashtag sets, community tags, language choices and measurement log live in `<profile_dir>/hashtags.md`**; read it first when it exists.

Platform limits change. The facts below were collected in late 2026 from the platforms' own help pages plus secondary sources; recheck them when something looks off.

## Facts the rules rest on
- YouTube: up to 3 hashtags show by the title; more than 60 hashtags = all ignored; misleading or unrelated hashtags and plain keyword lists in the description are policy violations. Tags play a minimal role (useful for misspellings); search ranks on title, tags, description, content and engagement; hashtags are not a ranking factor. Tags 500 characters, title 100, description 5000 bytes. #Shorts is not needed.
- TikTok: max **5 hashtags** per post (since Aug 2025). #fyp / #foryou work like any other hashtag, so they waste a slot. Caption + hashtags 4000 characters, only ~100 visible before "more". Signals include captions, sounds, hashtags, language and country (a caption in the audience's language helps reach that audience).
- Shorts reach = hook + retention; metadata mainly tells the platform the topic and catches some search. Long-form gets real search traffic (`<game> <boss>`).

## Per-video research (~10 min; for Shorts steps 1-2 are enough)
1. YouTube autocomplete (private window): type `<game>`, `<game> <boss>`, `<game> <audience language or country>`; note 3-5 phrases.
2. TikTok search: `<game> <boss>`, scroll to "Others searched for"; check the post count on the game's tag page and on one community tag for the channel's audience.
3. Long-form or bigger Shorts: open 3-5 top videos on that game/boss in the channel's language, note repeated title words and their tags.
4. Unsure between namings: Google Trends, YouTube Search, the channel's country, 90 days (variants are not merged, compare them separately).
5. Write the pack with the template below. Trending-hashtag lists are mostly irrelevant for niche single-player games.

Write the phrases you found at the top of the upload text (1-3 lines) so the owner sees where they came from. If a step could not be done (no browser access), say so instead of inventing search volumes.

## Template rules
- Title / caption line 1: `<hook> | <game name as in the game>`. The game (and the boss when it is the subject) must be in the first ~100 characters.
- Hashtags: **max 5 on every platform**, order matters (the first 3 may show by the YouTube title):
  `#<FullGameName> #<ShortName/Franchise> #<ContentType> [#<Genre>] [#<CommunityTag with visible activity>]`
  Content type follows the video: montage -> #BossFight / #GameMontage, lore -> #GameLore, funny -> #GamingMeme. No #fyp, #viral, #Shorts. A sound or trend tag only if the video uses that sound (it still counts in the 5).
- YouTube Tags field (never pasted into the description): full game name, short name, common misspellings and variants, boss, chapter, `<game> gameplay`, `<game> <audience language>`, the channel name. Under 500 characters.
- Long-form in a language other than English: add a translated English title + description in the platform's language settings; the main title stays in the channel's language with the game's own name.
- Check post counts in the app before locking a hashtag set for a game, then record the set in `<profile_dir>/hashtags.md`.

## Measure
Day 7 and day 28 per video: YouTube analytics (traffic source "YouTube Search" with its search terms, and how viewers find the Shorts) and TikTok analytics for the video (traffic sources including Search, search queries). Log date, video, platform, content type, hashtags, top 3 search terms, % search and % feed in a CSV whose path is noted in `<profile_dir>/hashtags.md`. Search terms that repeat but are not in the titles feed the next titles. Test one variable at a time over ~10 Shorts.
