# AI Agent ตัวแรกของคุณ (QR form → LINE)

Static page for the IESA S-Curve MBA รุ่น 6 class (11 Oct 2026). People scan the QR on the slide, type their
business and their answer, and press **ส่งเข้า LINE**. The page opens
`https://line.me/R/oaMessage/%40pngoung/?<text>`, so LINE shows the chat with @pngoung with the message already
typed. They press ส่ง in LINE. The page itself sends nothing to any server, and it has no analytics.

Message format (ลูกแพร matches on the first line, `#AIAGENT`, case-insensitive):

```
#AIAGENT IESA6
ธุรกิจ: <business>
อยากให้ผู้ช่วย AI ทำก่อน: <answer>
(ขอรับไอเดียการวางระบบ AI Agent ภายใน 24 ชม.)
```

Line breaks and repeated spaces inside the answers are collapsed to single spaces, so the message always has
exactly these four lines.

- **Config.** The campaigns live in the `#campaigns` JSON block in `index.html`. `?c=<campaignId>` picks one
  (case-insensitive). A missing or unknown id falls back to `default`. A future class needs only a new entry
  plus its own `?c=` link and QR.
- **Length guard.** A Thai character takes 9 characters in the link, and the link must stay under 2,000
  characters. Answers that fit inside the 160 and 300 character limits can still make the link too long, so the
  page shows the remaining room. If the text is too long, it blocks sending and shows "ลดอีก N ตัวอักษร".
- **Publish.** Publish as GitHub Pages repo `pgnoung/ai-agent-blueprint`. The slide QR points to
  `https://pgnoung.github.io/ai-agent-blueprint/?c=IESA6`.
- **Files.** `index.html`, `style.css` and `app.js`, plus `fonts/` (Mitr 500 and Noto Sans Thai Looped 400,
  self-hosted, OFL). There is no build step.
- **Test.** Run `python3 tests/form_test.py --shots <dir>`. It uses Playwright with Chrome at 390x844. It types
  Thai, intercepts the line.me navigation, and checks the exact URL and decoded text, the errors, the length
  guard and the campaign fallback.
