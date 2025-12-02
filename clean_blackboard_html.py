#!/usr/bin/env python3
# clean_html.py
# Usage: python3 clean_html.py INPUT.html [OUTPUT.html]

import re
import sys
from pathlib import Path

def main():
    if len(sys.argv) < 2:
        sys.exit("Usage: python3 clean_html.py INPUT.html [OUTPUT.html]")

    inp = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else inp.with_name(f"Cleaned_{inp.name}")
    html = inp.read_text(encoding="utf-8", errors="ignore")

    # 1) Remove <script>…</script>
    html = re.sub(r'(?is)<script\b[^>]*>.*?</script>', '', html)

    # Replace <h3…</h3>
    html = re.sub(
        r'<h3\b([^>]*)>(.*?)</h3>',
        r'<h5>\2</h5>',
        html,
        flags=re.DOTALL
    )

    html = re.sub(
        r'style="position:relative;"',
        r'style="position:relative; margin-bottom:0; padding-bottom:0;"',
        html, flags=re.DOTALL
    )

    html = re.sub(
        r'style="position:relative;"',
        r'style="position:relative; margin-bottom:0; padding-top:0; padding-bottom:0;"',
        html
    )

    html = re.sub(
        r'<li>\s*',
        r'<li style="padding:0;">',
        html
    )

    # 2) Remove <button>…</button>
    html = re.sub(r'(?is)<button\b[^>]*>.*?</button>', '', html)

    # 3) Simplify <div id="drv_XXXX" ...> → <div>
    html = re.sub(r'(?i)<div[^>]*\bid="drv_[0-9a-f]{4}"[^>]*>', '<div>', html)

    # 4) Replace hidden 1px spans with a single space
    html = re.sub(r'(?i)<span[^>]*font-size\s*:\s*1px[^>]*>[^<]+</span>', ' ', html)

    # 5) Unwrap labels, keep their inner content
    html = re.sub(r'(?is)<label\b[^>]*>(.*?)</label>', r'\1', html)

    # 6) Trim trailing spaces
    html = re.sub(r'[ \t]+$', '', html, flags=re.M)

    # remove double spaces
    html = re.sub(r'  ', ' ', html)
    html = re.sub(r'\s*</div>', '</div>\n', html)

    # Cut everything inside <body> up to the first question block
    m_body = re.search(r'(?is)<body\b[^>]*>', html)
    m_q = re.search(r'(?is)<div\b[^>]*\bclass\s*=\s*"[^"]*\btakeQuestionDiv\b[^"]*"', html)
    if not m_q:
        # fallback: match by the Blackboard id pattern if class scan fails
        m_q = re.search(r'(?is)<div\b[^>]*\bid="_\d+_1"\b[^>]*>', html)

    if m_body and m_q and m_q.start() > m_body.end():
        html = html[:m_body.start()] + '\n<body>\n\n' + html[m_q.start():]

    # Remove Blackboard "Save Answer" button spans
    html = re.sub(
        r'(?is)<span[^>]*class="[^"]*\bstepTitleRight\b[^"]*"[^>]*>.*?Save Answer.*?</span>',
        '\n',
        html
    )

    # Remove Blackboard footer ("Save and Submit" block and trailing content)
    html = re.sub(
        r'(?is)<div[^>]*\bid="bottomSubmitPlaceHolder"[^>]*>.*?(?=</body>)',
        '\n',
        html
    )

    # Remove fieldset box line: unwrap <legend>, drop <fieldset> tags
    html = re.sub(r'(?is)<legend\b[^>]*>(.*?)</legend>', r'\1', html)
    html = re.sub(r'(?is)</?fieldset\b[^>]*>', '', html)

    # Optional: drop the hidden anchor placeholders between questions
    html = re.sub(r'(?is)<a\b[^>]*\bclass\s*=\s*"[^"]*\bhidden\b[^"]*"[^>]*>.*?</a>', '', html)

    # 1) Flatten "A. <div>…</div>" inside vtbegenerated wrappers -> "A. …"
    html = re.sub(
        r'(?is)<div[^>]*class="[^"]*\bvtbegenerated\b[^"]*"[^>]*>\s*([A-Z])\.\s*<div>\s*(?:<p>)?(.*?)(?:</p>)?\s*</div>\s*</div>',
        r'\1. \2',
        html
    )

    # 7) Collapse 3+ blank lines into exactly 3
    html = re.sub(r'\n{3,}', '\n\n\n', html)

    print("Use <div style='page-break-before: always;'></div> to add page breaks")

    out.write_text(html, encoding="utf-8")
    print(f"Output: {out}")

if __name__ == "__main__":
    main()
