# Extraction brief: "who said what about whom" graph

Source: `C:\Users\Thanunchai\Desktop\Data\Claude Code\etc_diagnose\diagnose.md`. It is a Thai Election Commission (กกต.) ruling ที่ ๑๕๒๖/๒๕๖๙ about the 2567 Senate selection. Pages are marked `<!-- page N -->`. Read ONLY your assigned page range (use Read with offset/limit, or Grep for `<!-- page N -->` to find line numbers).

Respondent master list (ผู้ถูกร้องที่ 1–427 with names and roles): `C:\Users\THANUN~1\AppData\Local\Temp\claude\6af7f8799701ad5b\9a9d552e-9a75-4dc3-abfa-73c6a4c9cecc\scratchpad\respondents.json`. Fields: n, name, role.

Goal: extract a graph of WHO says/does WHAT about WHOM, grouped by the section (ประเด็นที่พิจารณา) it appears in, for an interactive network web page.

## Output

Write ONE JSON file (UTF-8, valid JSON, Thai text kept as Thai) to the path given in your task, with this shape:

```json
{
  "sections": [
    {"id": "g-surat", "parent": null, "title": "กลุ่มจังหวัดสุราษฎร์ธานี", "pages": [49, 51],
     "summary": "สรุปสั้น 1–3 ประโยค ว่าประเด็นนี้กล่าวหาอะไร และ กกต. เห็นอย่างไร"}
  ],
  "entities": [
    {"id": "W:12-26@g-surat", "label": "พยานรหัส ๑๒/๒๖", "type": "witness"},
    {"id": "P:นายสมชาย กุลากุล", "label": "นายสมชาย กุลากุล", "type": "person", "note": "บุคคลใกล้ชิดผู้สมัคร"},
    {"id": "O:พรรคภูมิใจไทย", "label": "พรรคภูมิใจไทย", "type": "org"}
  ],
  "edges": [
    {"section": "g-surat", "from": "W:12-26@g-surat", "to": "R212", "kind": "testimony",
     "verb": "ให้ถ้อยคำว่า", "text": "ผู้ถูกร้องที่ ๒๑๒ โทรแจ้งให้ไปรับเงิน ๓,๐๐๐ บาท หน้า ธ.ก.ส. วิภาวดี",
     "quote": "ให้ไปรับเงิน ๓,๐๐๐ บาท", "page": 50}
  ]
}
```

### IDs (must follow exactly, so files from different agents merge)
- Respondent: `R<arabic number>`, e.g. ผู้ถูกร้องที่ ๒๑๒ → `R212`. Do NOT add respondents to `entities` (they come from the master list).
- Witness: `W:<code with - instead of />@<top section id>`, e.g. พยานรหัส ๑๒/๒๖ in g-surat → `W:12-26@g-surat`. Arabic digits in IDs, Thai digits in labels. Witness codes are reused across different cases, so scope by section.
- Other named person (not a numbered respondent): `P:<full name as written, with title>`.
- Organisation / party / company / hotel / agency: `O:<name>`. Use `O:กกต.` for the Election Commission (คณะกรรมการการเลือกตั้ง). Use `O:กรมสอบสวนคดีพิเศษ` for DSI.
- Unnamed complainant: `O:ผู้ร้อง (<section id>)`.

### Section IDs (use these; add children as `<parent>/<suffix>` with `parent` set, e.g. `g-nbl/c2-i3` for กรณีที่ ๒ ประเด็นที่ ๓)
- `intro` ข้อกล่าวหา ๗ ข้อ และการรวมสำนวน ๓๔ กรณี (p21–31)
- `a12-plan` ข้อกล่าวหาที่ ๑–๒: แผนการภาพรวมของคณะบุคคล (p31–32)
- `a12-krungsri` โรงแรมกรุงศรีริเวอร์ จ.พระนครศรีอยุธยา (p32–33)
- `a12-klongsuanplu` คลองสวนพลูรีสอร์ท จ.พระนครศรีอยุธยา (p33–34)
- `a12-wangyao` โรงแรมวังยาว ริเวอร์ไซด์ รีสอร์ท จ.นครนายก (p34–36)
- `a12-thara` โรงแรมธาราแกรนด์ จ.ปทุมธานี (p36–39) — children: `a12-thara/nbl`, `a12-thara/nst`, `a12-thara/phuket`
- `a12-pinehurst` โรงแรมไพน์เฮิร์สท จ.ปทุมธานี (p39–40)
- `a12-srinanaporn` บริษัท ศรีนานาพร มาร์เก็ตติ้ง จ.สมุทรสาคร (p40–41)
- `a12-ruling` การวินิจฉัยข้อกล่าวหาที่ ๑–๒ (p41–46)
- `a12-naphintorn` กรณีนายนภินทร ศรีสรรพางค์ (p46)
- `a12-withee` กรณีนายวิถี สุพิทักษ์ (p46–47)
- `a12-pichai` กรณีนายพิชัย ชมภูพล (p47–48)
- `g-surat` สุราษฎร์ธานี, `g-uthai` อุทัยธานี, `g-nst` นครศรีธรรมราช, `g-songkhla` สงขลา, `g-nbl` หนองบัวลำภู, `g-singburi` สิงห์บุรี, `g-phuket` ภูเก็ต, `g-ratchaburi` ราชบุรี, `g-nakhonphanom` นครพนม, `g-sukhothai` สุโขทัย (ข้อกล่าวหาที่ ๓–๗ การกระทำเป็นกลุ่ม, p48–73)
- `i-<N>` การกระทำรายบุคคลลำดับที่ N (N = 11…37, p73–89); combined headings like "ลำดับที่ ๓๑ ๓๒ ๓๓ ๓๕ ๓๖" → `i-31-36`; "๑๓ ๑๔ ๑๕" → `i-13-15`; "๑๖ และ ๑๗" → `i-16-17`
- `s-<N>` สำนวนแยกเรื่อง/ประเด็น "(ลำดับที่ N)" (p89–105); use `s-misc` for text not under one.

### Edge kinds
- `testimony` — a witness (or anyone) gives a statement mentioning someone. from = speaker, to = person spoken about. One edge per (speaker, subject, distinct claim).
- `defense` — a respondent's own explanation (ชี้แจง / ให้ถ้อยคำแก้ข้อกล่าวหา). from = respondent; to = the respondent themself, or another person their explanation is about.
- `accusation` — a complainant / agency / DSI alleges something about someone. from = accuser, to = accused.
- `action` — something someone DID to someone, as described in the evidence: transferred money, instructed, invited, handed out vote slips (โพย), paid for rooms, etc. from = actor, to = target. Put the amount, date and channel in `text`. `verb` examples: "โอนเงินให้", "สั่งการ", "ชักชวน", "แจกโพย", "จ่ายเงิน".
- `finding` — กกต.'s conclusion about a person in that section (เชื่อได้ว่ากระทำผิด / ฟังไม่ได้ / พยานหลักฐานไม่พอ). from = `O:กกต.`, to = the person. In `text`, say whether it was found to be an offence and under which มาตรา.
- `ruling` — ONLY for pages 106–114 (the final orders): from = `O:กกต.`, to = the person; `verb` = e.g. "สั่งเพิกถอนสิทธิสมัคร", "ให้ดำเนินคดีอาญา", "ยกคำร้อง", "ให้ส่งศาลฎีกา"; `text` = the order in one sentence, including the duration if any (e.g. "เพิกถอนสิทธิสมัครรับเลือก ๑๐ ปี"). When an order lists many people (e.g. "ผู้ถูกร้องที่ ๑ ถึงผู้ถูกร้องที่ ๓๐"), expand ranges into one edge per respondent.

### Rules
- **VERBATIM REQUIREMENT (overrides anything above):** `text` must be copied EXACTLY, character for character, from diagnose.md. It should be the original sentence or clause that states the claim, testimony, action, finding or order; do not summarise, paraphrase or reword. Thai sentences can be very long. Pick the shortest contiguous run that still carries the meaning, from about 40 to 400 characters, and cut at a natural boundary (a space). Do not join non-adjacent pieces with "…". If one passage supports several edges, reuse the same exact text.
- The same verbatim rule applies to section `summary` (copy the opening sentence of the section that states what it is about, ≤ 400 chars) and to `orders[].text` (≤ 500 chars).
- `quote`: omit it (no longer used).
- `page`: the page where `text` STARTS (the nearest `<!-- page N -->` marker above it). If the passage crosses a page break, still give the starting page; the build script re-checks it.
- Never include the `<!-- page N -->` marker or line breaks inside `text`.
- When a statement names a group ("ผู้ถูกร้องที่ ๑๔๕ ผู้ถูกร้องที่ ๑๔๘ … และผู้ถูกร้องที่ ๑๔๗"), create one edge per person, all with the same text. Expand "ผู้ถูกร้องที่ X ถึงผู้ถูกร้องที่ Y" into each number, but if a range is longer than 40 people, instead make ONE edge to a group entity `O:กลุ่มผู้ถูกร้อง X–Y` (type "group") and mention the range in its note.
- Be thorough: cover every witness, respondent explanation, money transfer, instruction and finding in your pages. Merge repeats of the identical claim.
- Copy names exactly as written in the document.
- Check the JSON is valid before finishing (for example run `python -I -c "import json,sys;json.load(open(sys.argv[1],encoding='utf-8'))" <file>`).

Final reply (≤ 120 words): the file path, counts of sections / entities / edges, and anything ambiguous you had to decide.
